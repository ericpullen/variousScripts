# Disk Space Monitor with Pushover Notifications

A Swift program that monitors disk usage and sends push notifications to your iPhone/Android when disk space reaches a specified threshold. Built for macOS with native APIs for accurate disk space reporting.

## Features

- Monitors disk usage at configurable intervals
- **Accurate disk space reporting** - Uses macOS native APIs to show available space including purgeable space (matches Finder's "Get Info" display)
- Sends Pushover push notifications when threshold is exceeded
- Configurable alert cooldown period to prevent notification spam
- JSON-based configuration
- Monitors any mount point (default: root filesystem)
- Automatic alert reset when usage drops below threshold
- Clean exit on Ctrl-C

## Requirements

- macOS (uses native Foundation APIs)
- Swift compiler (included with Xcode Command Line Tools)
- Pushover account and app

## Installation

1. **Install Xcode Command Line Tools** (if not already installed):
```bash
xcode-select --install
```

2. **Compile the program**:
```bash
swiftc -o disk_monitor disk_monitor.swift
```

Or if you prefer to run it directly as a script:
```bash
chmod +x disk_monitor.swift
./disk_monitor.swift
```

3. **Set up Pushover**:
   - Install the Pushover app on your iPhone/Android
   - Create a Pushover account and note your **User Key**
   - Register a new application at https://pushover.net/apps/build to get an **API Token**

4. **Configure the monitor**:
   - Edit `config.json` with your Pushover credentials
   - Adjust threshold and check interval as needed

## Configuration

Edit `config.json`:

```json
{
  "pushover_token": "YOUR_APP_TOKEN_HERE",          // Your Pushover app token
  "pushover_user_key": "YOUR_USER_KEY_HERE",        // Your Pushover user key
  "threshold_percent": 90,                          // Alert when disk usage exceeds this %
  "check_interval_seconds": 60,                     // How often to check (in seconds)
  "mount_point": "/",                               // Which disk/mount point to monitor
  "alert_cooldown_minutes": 60,                     // Wait this long before re-alerting
  "pushover_priority": 1,                           // 0=normal, 1=high (bypass quiet hours)
  "pushover_sound": "updown"                        // Notification sound
}
```

### Configuration Options Explained

- **pushover_token**: API token from your Pushover application
- **pushover_user_key**: Your user key from Pushover settings
- **threshold_percent**: Percentage (0-100) that triggers alerts
- **check_interval_seconds**: How frequently to check disk usage
- **mount_point**: Which disk to monitor (`/` for root, `/Volumes/External` for external drives, etc.)
- **alert_cooldown_minutes**: Prevents repeated alerts; waits this long before sending another alert
- **pushover_priority**: 
  - `-2`: No notification (badge only)
  - `-1`: Quiet notification
  - `0`: Normal priority
  - `1`: High priority (bypasses quiet hours)
  - `2`: Emergency (requires acknowledgment)
- **pushover_sound**: Options include: `pushover`, `bike`, `bugle`, `cashregister`, `classical`, `cosmic`, `falling`, `gamelan`, `incoming`, `intermission`, `magic`, `mechanical`, `pianobar`, `siren`, `spacealarm`, `tugboat`, `alien`, `climb`, `persistent`, `echo`, `updown`, `none`

## Usage

### Run the compiled executable:
```bash
./disk_monitor
```

### Run as a script (no compilation needed):
```bash
./disk_monitor.swift
```

### Run with custom config file:
```bash
./disk_monitor /path/to/custom_config.json
```

### Run in background:
```bash
nohup ./disk_monitor > disk_monitor.log 2>&1 &
```

### Stop the program:
- Press **Ctrl-C** to exit gracefully
- Or if running in background:
```bash
# Find the process
ps aux | grep disk_monitor

# Kill it
kill <PID>
```

## Running as a Launch Agent (macOS)

To have this run automatically at startup on macOS:

1. **Compile the program** (if not already compiled):
```bash
swiftc -o disk_monitor disk_monitor.swift
```

2. **Create a plist file** at `~/Library/LaunchAgents/com.diskmonitor.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.diskmonitor</string>
    <key>ProgramArguments</key>
    <array>
        <string>/full/path/to/disk_monitor</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/full/path/to/directory/with/config</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/diskmonitor.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/diskmonitor.err</string>
</dict>
</plist>
```

3. **Update the paths** in the plist to match your system (use absolute paths)

4. **Load the agent**:
```bash
launchctl load ~/Library/LaunchAgents/com.diskmonitor.plist
```

5. **To unload**:
```bash
launchctl unload ~/Library/LaunchAgents/com.diskmonitor.plist
```

## Output Example

```
============================================================
Disk Space Monitor Starting
============================================================
Mount Point: /
Threshold: 90%
Check Interval: 60 seconds
Alert Cooldown: 60 minutes
============================================================

[2025-11-18 10:30:15] /: 85.2% used ✓
[2025-11-18 10:31:15] /: 89.8% used ✓
[2025-11-18 10:32:15] /: 91.3% used ⚠️  THRESHOLD EXCEEDED
Sending alert...
✓ Pushover notification sent successfully
[2025-11-18 10:33:15] /: 92.1% used ⚠️  THRESHOLD EXCEEDED
Alert cooldown active (last sent: 2025-11-18 10:32:15)
```

## Troubleshooting

**"Config file not found"**
- The program will create an example `config.json` for you. Edit it with your credentials.

**"Missing required config field"**
- Make sure your `config.json` includes both `pushover_token` and `pushover_user_key`

**"swiftc: command not found"**
- Install Xcode Command Line Tools: `xcode-select --install`

**Notifications not arriving**
- Verify your API token and user key are correct
- Check that the Pushover app is installed and logged in
- Test manually with curl:
```bash
curl -s \
  --form-string "token=YOUR_TOKEN" \
  --form-string "user=YOUR_USER_KEY" \
  --form-string "message=Test" \
  https://api.pushover.net/1/messages.json
```

**High CPU usage**
- Increase `check_interval_seconds` to check less frequently

**Ctrl-C doesn't exit**
- The program should exit cleanly on Ctrl-C. If it doesn't, you can force quit with `kill -9 <PID>`

## Notes

- **Accurate Disk Space**: This program uses macOS native APIs (`NSURLResourceKey.volumeAvailableCapacityForImportantUsageKey`) to get disk space that matches what you see in Finder's "Get Info" window, including purgeable space (Time Machine snapshots, caches, etc.)
- The program resets the alert flag when disk usage drops below the threshold
- Alert cooldown prevents notification spam if disk stays above threshold
- High priority (priority: 1) will notify you even during iOS Focus/Do Not Disturb
- For emergency alerts requiring acknowledgment, use priority: 2
- The program responds to Ctrl-C within 0.1 seconds for clean shutdown

## Technical Details

- Built with Swift using Foundation framework
- Uses `URLSession` for HTTP requests (no external dependencies)
- Uses native macOS disk space APIs for accurate reporting
- Signal handling for clean exit on Ctrl-C

## License

Free to use and modify as needed.
