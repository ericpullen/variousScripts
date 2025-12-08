#!/usr/bin/env python3
"""
GoFan Event Scraper → ICS Calendar Generator

Scrapes event data from a GoFan school page and generates a subscribable ICS calendar file.

Usage:
    python gofan_scraper.py "https://gofan.co/app/school/KY6207?activity=Basketball&gender=Girls"
    python gofan_scraper.py URL -o my_calendar.ics --calendar-name "Dragons Basketball"
    
Requirements:
    pip install playwright icalendar beautifulsoup4
    playwright install chromium
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event, vText

# Default timezone for Kentucky
DEFAULT_TZ = ZoneInfo("America/Kentucky/Louisville")


def scrape_gofan_events(url: str, headless: bool = True, debug: bool = False) -> list[dict]:
    """
    Scrape events from a GoFan school page.
    
    Returns a list of event dictionaries with keys:
    - title: Event name
    - date: Date string
    - time: Time string  
    - venue: Location/venue name
    - address: Full address if available
    - opponent: Opponent team if parseable
    - ticket_url: Link to buy tickets
    """
    from playwright.sync_api import sync_playwright
    from bs4 import BeautifulSoup
    
    events = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        
        print(f"Loading {url}...")
        # Use domcontentloaded instead of networkidle (GoFan has persistent connections)
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Wait for the page to actually render content
        # Try to wait for event-related elements to appear
        print("Waiting for content to load...")
        try:
            # Wait for any of these selectors that might indicate events loaded
            page.wait_for_selector('a[href*="/event/"], [class*="event"], [class*="Event"]', timeout=15000)
            print("Found event-related elements")
        except:
            print("No event selectors found, continuing anyway...")
        
        # Give React/JS a moment to finish rendering
        page.wait_for_timeout(3000)
        
        # Scroll to load any lazy-loaded content
        for i in range(3):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)
            print(f"Scroll {i+1}/3...")
        
        content = page.content()
        
        if debug:
            debug_path = Path("gofan_debug.html")
            debug_path.write_text(content)
            print(f"Debug: saved page HTML to {debug_path}")
        
        soup = BeautifulSoup(content, 'html.parser')
        
        # Strategy 1: Look for __NEXT_DATA__ JSON (Next.js apps often embed data here)
        next_data = soup.find('script', id='__NEXT_DATA__')
        if next_data:
            try:
                data = json.loads(next_data.string)
                events = extract_events_from_nextdata(data, url)
                if events:
                    print(f"Extracted {len(events)} events from Next.js data")
                    browser.close()
                    return events
            except json.JSONDecodeError:
                pass
        
        # Strategy 2: Look for event cards using data-testid (GoFan's clean structure)
        event_cards = soup.select('[data-testid="event-card"]')
        print(f"Found {len(event_cards)} event cards with data-testid")
        
        for card in event_cards:
            event_data = extract_event_from_card_structured(card, url)
            if event_data:
                events.append(event_data)
        
        # Strategy 3: Parse visible text structure if DOM parsing fails
        if not events:
            print("Trying text-based extraction...")
            events = extract_events_from_text(soup, url)
        
        browser.close()
    
    return events


def extract_events_from_nextdata(data: dict, base_url: str) -> list[dict]:
    """Extract events from Next.js __NEXT_DATA__ JSON."""
    events = []
    
    def find_events(obj, path=""):
        """Recursively search for event-like objects."""
        if isinstance(obj, dict):
            # Check if this looks like an event
            if any(k in obj for k in ['eventName', 'eventDate', 'startTime', 'venueName']):
                events.append({
                    'title': obj.get('eventName') or obj.get('name') or obj.get('title', ''),
                    'date': obj.get('eventDate') or obj.get('date') or obj.get('startDate', ''),
                    'time': obj.get('startTime') or obj.get('time', ''),
                    'venue': obj.get('venueName') or obj.get('venue', ''),
                    'address': obj.get('venueAddress') or obj.get('address', ''),
                    'ticket_url': obj.get('ticketUrl') or obj.get('url', ''),
                    'opponent': obj.get('opponent') or obj.get('awayTeam', ''),
                })
            for k, v in obj.items():
                find_events(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                find_events(item, f"{path}[{i}]")
    
    find_events(data)
    return events


def extract_event_from_card_structured(card, base_url: str) -> dict | None:
    """
    Extract event data from a GoFan event card using data-testid attributes.
    
    GoFan's structure:
    - data-testid="event-tag" -> Home/Away
    - data-testid="day-of-week" -> Mon, Tue, etc.
    - data-testid="month-day-of-year" -> Dec 8, Jan 5
    - data-testid="year" -> 2026 (only shown for future years)
    - data-testid="time" -> 7:00 PM
    - data-testid="event-name" -> Oldham County Colonels vs Kentucky Country Bearcats
    - data-testid="sport" -> Basketball
    - data-testid="activity-levels" -> Girls JV/Varsity
    - data-testid="more-info" -> Oldham County High School (Buckner, KY)
    - Buy tickets link -> /event/5212753?schoolId=KY6207
    """
    event = {}
    
    # Home/Away
    tag = card.select_one('[data-testid="event-tag"]')
    if tag:
        event['home_away'] = tag.get_text(strip=True)
    
    # Date components
    day_of_week = card.select_one('[data-testid="day-of-week"]')
    month_day = card.select_one('[data-testid="month-day-of-year"]')
    year_elem = card.select_one('[data-testid="year"]')
    time_elem = card.select_one('[data-testid="time"]')
    
    if month_day:
        date_str = month_day.get_text(strip=True)
        if year_elem:
            year_text = year_elem.get_text(strip=True)
            # GoFan shows "2026" but means 2025 for Jan-Jul dates
            date_str = f"{date_str} {year_text}"
        event['date'] = date_str
    
    if time_elem:
        event['time'] = time_elem.get_text(strip=True)
    
    # Event name (matchup)
    event_name = card.select_one('[data-testid="event-name"]')
    if event_name:
        full_name = event_name.get_text(strip=True)
        event['full_name'] = full_name
        
        # Parse the matchup to create a cleaner title
        # Format: "Oldham County Colonels vs Kentucky Country Bearcats"
        # or "Southern Trojans vs Oldham County" for away games
        if ' vs ' in full_name:
            parts = full_name.split(' vs ')
            if event.get('home_away') == 'Home':
                # Home game: we're the first team, opponent is second
                opponent = parts[1].strip() if len(parts) > 1 else ''
                event['title'] = f"vs {opponent}"
                event['opponent'] = opponent
            else:
                # Away game: opponent is first team
                opponent = parts[0].strip()
                event['title'] = f"@ {opponent}"
                event['opponent'] = opponent
        else:
            # Special event (e.g., "Ronald McDonald House Classic")
            event['title'] = full_name
    
    # Sport and level
    sport = card.select_one('[data-testid="sport"]')
    if sport:
        event['sport'] = sport.get_text(strip=True)
    
    activity_levels = card.select_one('[data-testid="activity-levels"]')
    if activity_levels:
        levels = activity_levels.get_text(strip=True)
        event['levels'] = levels
        # Add prefix based on gender
        if 'Girls' in levels:
            event['title'] = f"GBB: {event.get('title', '')}"
        elif 'Boys' in levels:
            event['title'] = f"BBB: {event.get('title', '')}"
    
    # Location - this is the key new field!
    more_info = card.select_one('[data-testid="more-info"]')
    if more_info:
        location_text = more_info.get_text(strip=True)
        event['venue'] = location_text
    
    # Ticket URL
    buy_link = card.select_one('a[href*="/event/"]')
    if buy_link:
        href = buy_link.get('href', '')
        if href.startswith('/'):
            href = f"https://gofan.co{href}"
        event['ticket_url'] = href
    
    # Only return if we have meaningful data
    if not event.get('date') or not event.get('title'):
        return None
    
    return event


def extract_event_from_card(card, base_url: str) -> dict | None:
    """Extract event data from an HTML card element."""
    event = {}
    
    # Get the link
    link = card.get('href') if card.name == 'a' else None
    if not link:
        link_elem = card.find('a', href=True)
        link = link_elem['href'] if link_elem else None
    
    if link:
        if link.startswith('/'):
            link = f"https://gofan.co{link}"
        event['ticket_url'] = link
    
    # Get text content
    text = card.get_text(separator=' ', strip=True)
    
    # Try to find date patterns - look for "Mon Dec 8" or "Tue Jan 5" style
    # Pattern: Day-of-week Month Day (optional year) Time
    date_pattern = r'((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}(?:\s+\d{4})?)'
    date_match = re.search(date_pattern, text)
    if date_match:
        event['date'] = date_match.group(1)
    
    # Try to find time patterns
    time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM))', text, re.I)
    if time_match:
        event['time'] = time_match.group(1)
    
    # Extract the matchup/title
    # Look for pattern: "Team1 vs Team2" or "Team1 vs Team2 Sport"
    vs_pattern = r'([A-Za-z\s]+(?:Colonels|Eagles|Bears|Panthers|Cougars|Mustangs|Trojans|Generals|Hawks|Bulldogs|Raiders|Bearcats|Titans|Centurions|Juggernauts)?)\s+vs\s+([A-Za-z\s]+?)(?:\s+Basketball|\s+Buy|\s*$)'
    vs_match = re.search(vs_pattern, text)
    if vs_match:
        team1, team2 = vs_match.groups()
        team1 = team1.strip()
        team2 = team2.strip()
        
        # Determine if home or away
        if 'Home' in text[:20]:
            event['title'] = f"vs {team2}"
            event['opponent'] = team2
            event['home_away'] = 'Home'
        elif 'Away' in text[:20]:
            event['title'] = f"@ {team1.replace('Oldham County Colonels', '').strip()}"
            event['opponent'] = team1.replace('Oldham County Colonels', '').strip()
            event['home_away'] = 'Away'
        else:
            event['title'] = f"{team1} vs {team2}"
    else:
        # Fallback: try to get a reasonable title
        # Remove common noise words and truncate
        title = text
        for noise in ['Buy tickets', 'Home', 'Away', 'Today\'s events', 'Upcoming events', 'All day']:
            title = title.replace(noise, '')
        # Get first meaningful chunk
        title = re.sub(r'\s+', ' ', title).strip()
        if len(title) > 80:
            title = title[:80] + '...'
        event['title'] = title
    
    # Check for Girls vs Boys basketball
    if 'Girls' in text:
        event['sport'] = 'Girls Basketball'
        if 'title' in event and 'Basketball' not in event['title']:
            event['title'] = f"GBB: {event['title']}"
    elif 'Boys' in text:
        event['sport'] = 'Boys Basketball'
        if 'title' in event and 'Basketball' not in event['title']:
            event['title'] = f"BBB: {event['title']}"
    
    # Check for JV
    if 'JV' in text:
        event['level'] = 'JV/Varsity'
    
    return event if event.get('ticket_url') or event.get('title') else None


def extract_events_from_text(soup, base_url: str) -> list[dict]:
    """Fallback: extract events by parsing visible page text."""
    events = []
    
    # Look for any links to /event/ pages
    for link in soup.find_all('a', href=re.compile(r'/event/')):
        parent = link.find_parent(['div', 'li', 'article'])
        if parent:
            text = parent.get_text(separator='\n', strip=True)
            
            event = {
                'ticket_url': link['href'] if link['href'].startswith('http') else f"https://gofan.co{link['href']}",
                'title': link.get_text(strip=True) or 'Game',
            }
            
            # Parse text for date/time
            lines = text.split('\n')
            for line in lines:
                if re.search(r'\d{1,2}/\d{1,2}|\w+\s+\d{1,2}', line):
                    event['date'] = line.strip()
                if re.search(r'\d{1,2}:\d{2}', line):
                    event['time'] = re.search(r'\d{1,2}:\d{2}\s*(?:AM|PM)?', line, re.I).group()
            
            events.append(event)
    
    return events


def create_ics_calendar(events: list[dict], calendar_name: str = "GoFan Events") -> Calendar:
    """
    Create an ICS calendar from a list of events.
    """
    cal = Calendar()
    cal.add('prodid', '-//GoFan Scraper//gofan-to-ics//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('x-wr-calname', calendar_name)
    cal.add('x-wr-timezone', 'America/Kentucky/Louisville')
    
    for evt_data in events:
        event = Event()
        event.add('summary', evt_data.get('title', 'Game'))
        
        # Parse date/time
        dt_start = parse_event_datetime(evt_data.get('date', ''), evt_data.get('time', ''))
        if dt_start:
            event.add('dtstart', dt_start)
            # Assume 2-hour duration for games
            event.add('dtend', dt_start + timedelta(hours=2))
        
        # Location - use venue from the structured extraction
        if evt_data.get('venue'):
            event.add('location', evt_data['venue'])
        
        # URL to tickets
        if evt_data.get('ticket_url'):
            event.add('url', evt_data['ticket_url'])
        
        # Description
        desc_parts = []
        if evt_data.get('opponent'):
            desc_parts.append(f"vs {evt_data['opponent']}")
        if evt_data.get('ticket_url'):
            desc_parts.append(f"Tickets: {evt_data['ticket_url']}")
        if desc_parts:
            event.add('description', '\n'.join(desc_parts))
        
        # Generate a unique ID
        uid = f"{evt_data.get('date', 'unknown')}-{evt_data.get('title', 'event')}@gofan-scraper"
        uid = re.sub(r'[^a-zA-Z0-9@.-]', '', uid)
        event.add('uid', uid)
        
        cal.add_component(event)
    
    return cal


def parse_event_datetime(date_str: str, time_str: str) -> datetime | None:
    """
    Parse various date/time formats from GoFan.
    
    Handles formats like:
    - "Mon Dec 8" -> December 8, current school year
    - "Tue Jan 5 2026" -> January 5, 2026 (explicit year, but probably means 2025)
    - "December 8, 2024" -> as written
    """
    if not date_str:
        return None
    
    # Clean up date string
    date_str = date_str.strip()
    
    # Handle relative dates
    today = datetime.now()
    if 'today' in date_str.lower():
        parsed_date = today
    elif 'tomorrow' in date_str.lower():
        parsed_date = today + timedelta(days=1)
    else:
        parsed_date = None
        
        # First, try to extract components using regex for flexible parsing
        # Pattern: optional day-of-week, month name, day number, optional year
        pattern = r'(?:\w{3}\s+)?(\w{3,9})\s+(\d{1,2})(?:\s+(\d{4}))?'
        match = re.search(pattern, date_str)
        
        if match:
            month_str, day_str, year_str = match.groups()
            
            # Parse month
            month_map = {
                'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
                'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
                'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
                'july': 7, 'august': 8, 'september': 9, 'october': 10, 
                'november': 11, 'december': 12
            }
            
            month = month_map.get(month_str.lower())
            if month:
                day = int(day_str)
                
                # Determine the year
                if year_str:
                    year = int(year_str)
                    # GoFan seems to show 2026 for what should be 2025
                    # If the year is more than 1 year in the future, it's probably wrong
                    if year > today.year + 1:
                        year = today.year + 1 if month < 7 else today.year
                else:
                    # No year specified - figure out based on school year logic
                    # School year runs Aug-Jul, so:
                    # - Aug-Dec dates are current calendar year
                    # - Jan-Jul dates are next calendar year
                    if month >= 8:  # Aug-Dec
                        year = today.year
                    else:  # Jan-Jul
                        year = today.year + 1
                        # But if we're already in that year, use current year
                        if today.month <= 7:
                            year = today.year
                
                try:
                    parsed_date = datetime(year, month, day)
                except ValueError:
                    pass
        
        # Fallback: try standard formats
        if not parsed_date:
            date_formats = [
                "%B %d, %Y",    # January 15, 2025
                "%b %d, %Y",    # Jan 15, 2025
                "%m/%d/%Y",     # 01/15/2025
                "%m/%d/%y",     # 01/15/25
                "%Y-%m-%d",     # 2025-01-15
            ]
            
            for fmt in date_formats:
                try:
                    parsed_date = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue
    
    if not parsed_date:
        return None
    
    # Parse time
    if time_str:
        time_str = time_str.strip().upper()
        time_formats = [
            "%I:%M %p",   # 7:00 PM
            "%I:%M%p",    # 7:00PM
            "%I %p",      # 7 PM
            "%H:%M",      # 19:00
        ]
        
        for fmt in time_formats:
            try:
                parsed_time = datetime.strptime(time_str, fmt)
                parsed_date = parsed_date.replace(
                    hour=parsed_time.hour,
                    minute=parsed_time.minute
                )
                break
            except ValueError:
                continue
    
    return parsed_date.replace(tzinfo=DEFAULT_TZ)


def get_sample_events() -> list[dict]:
    """Return sample events for testing ICS generation."""
    return [
        {
            'title': 'Girls Basketball vs North Oldham',
            'date': 'December 12, 2024',
            'time': '6:00 PM',
            'venue': 'South Oldham High School Gym',
            'address': '6403 W Highway 146, Crestwood, KY 40014',
            'ticket_url': 'https://gofan.co/event/123456',
            'opponent': 'North Oldham',
        },
        {
            'title': 'Girls Basketball vs Oldham County',
            'date': 'December 17, 2024',
            'time': '7:30 PM',
            'venue': 'South Oldham High School Gym',
            'address': '6403 W Highway 146, Crestwood, KY 40014',
            'ticket_url': 'https://gofan.co/event/123457',
            'opponent': 'Oldham County',
        },
        {
            'title': 'Girls Basketball @ Eastern',
            'date': 'January 3, 2025',
            'time': '6:00 PM',
            'venue': 'Eastern High School',
            'ticket_url': 'https://gofan.co/event/123458',
            'opponent': 'Eastern',
        },
        {
            'title': 'Girls Basketball vs Ballard',
            'date': 'January 10, 2025', 
            'time': '7:30 PM',
            'venue': 'South Oldham High School Gym',
            'address': '6403 W Highway 146, Crestwood, KY 40014',
            'ticket_url': 'https://gofan.co/event/123459',
            'opponent': 'Ballard',
        },
    ]


def main():
    parser = argparse.ArgumentParser(
        description="Scrape GoFan events to ICS calendar",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    %(prog)s "https://gofan.co/app/school/KY6207?activity=Basketball&gender=Girls"
    %(prog)s URL -o dragons_basketball.ics --calendar-name "Dragons Girls Basketball"
    %(prog)s --test  # Generate sample calendar for testing
        """
    )
    parser.add_argument("url", nargs='?', help="GoFan school page URL")
    parser.add_argument("-o", "--output", default="gofan_events.ics", help="Output ICS file path")
    parser.add_argument("--no-headless", action="store_true", help="Run browser in visible mode (for debugging)")
    parser.add_argument("--debug", action="store_true", help="Save debug HTML file")
    parser.add_argument("--calendar-name", default="GoFan Events", help="Calendar display name")
    parser.add_argument("--test", action="store_true", help="Generate calendar with sample events (no scraping)")
    
    args = parser.parse_args()
    
    if args.test:
        print("Generating test calendar with sample events...")
        events = get_sample_events()
    elif args.url:
        print(f"Scraping events from: {args.url}")
        events = scrape_gofan_events(args.url, headless=not args.no_headless, debug=args.debug)
    else:
        parser.print_help()
        sys.exit(1)
    
    print(f"\nFound {len(events)} events:")
    for evt in events:
        print(f"  - {evt.get('title', 'Unknown')} | {evt.get('date', '?')} {evt.get('time', '')}")
    
    if events:
        cal = create_ics_calendar(events, args.calendar_name)
        
        output_path = Path(args.output)
        with open(output_path, 'wb') as f:
            f.write(cal.to_ical())
        
        print(f"\n✓ Calendar saved to: {output_path.absolute()}")
        print(f"\nTo subscribe in Apple Calendar:")
        print(f"  1. Host this file at a URL (GitHub Gist, Dropbox, etc.)")
        print(f"  2. In Calendar.app: File → New Calendar Subscription")
        print(f"  3. Paste the URL")
    else:
        print("\nNo events found. Try running with --debug to inspect the page HTML.")


if __name__ == "__main__":
    main()
