import boto3
import json
import requests
from datetime import datetime, timedelta
import pandas as pd
import os
import hashlib
from pathlib import Path
import re

def list_available_price_lists(service_code='AmazonEC2', date=datetime.now(), currency_code='USD'):
    """
    List available AWS price lists for a given service code and date.
    
    Args:
        service_code (str): AWS service code (default: AmazonEC2)
        date (datetime): Date for which to query pricing (default: current date)
        currency_code (str): Currency code (default: USD)
    
    Returns:
        list: Available price lists
    """
    client = boto3.client('pricing', region_name='us-east-1')  # Pricing API is only available in us-east-1
    
    # Format date according to AWS requirements - YYYY-MM-DD
    formatted_date = date.strftime('%Y-%m-%d')
    
    params = {
        'ServiceCode': service_code,
        'CurrencyCode': currency_code,
        'EffectiveDate': formatted_date,
        'RegionCode': 'us-east-1',
        'MaxResults': 100,  # Adjust as needed
    }
    
    available_price_lists = []
    next_token = None
    
    try:
        while True:
            if next_token:
                params['NextToken'] = next_token
            
            response = client.list_price_lists(**params)
            available_price_lists.extend(response.get('PriceLists', []))
            
            next_token = response.get('NextToken')
            if not next_token:
                break
    except Exception as e:
        print(f"Error querying price lists for date {formatted_date}: {str(e)}")
        return []
    
    return available_price_lists

def download_price_list(price_list_url, service_code='AmazonEC2'):
    """
    Download a price list from the given URL, using caching to avoid repeated downloads.
    
    Args:
        price_list_url (str): URL to the price list
        service_code (str): AWS service code (default: AmazonEC2)
    
    Returns:
        dict: Price list data
    """
    # Create cache directory if it doesn't exist
    cache_dir = Path('cache')
    cache_dir.mkdir(exist_ok=True)
    
    # Extract the date/timestamp from the URL
    # URL format example: https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/20250408165718/index.json
    match = re.search(r'/(\d{14})/', price_list_url)
    if not match:
        raise ValueError(f"Could not extract date from price list URL: {price_list_url}")
    
    timestamp = match.group(1)
    cache_file = cache_dir / f"{service_code}_{timestamp}.json"
    
    # Check if we have a cached version
    if cache_file.exists():
        print(f"Using cached price list from {cache_file}")
        with open(cache_file, 'r') as f:
            return json.load(f)
    
    # If not cached, download the file
    print(f"Downloading price list from {price_list_url}")
    response = requests.get(price_list_url)
    response.raise_for_status()  # Raise exception for HTTP errors
    
    price_list_data = response.json()
    
    # Cache the downloaded data
    with open(cache_file, 'w') as f:
        json.dump(price_list_data, f, indent=3)
    
    return price_list_data

def analyze_ec2_pricing_options(price_list_data, region='us-east-1'):
    """
    Analyze which EC2 instances in the specified region are eligible for RIs and which are only 
    available with Savings Plans.
    
    Args:
        price_list_data (dict): Price list data dictionary
        region (str): AWS region (default: us-east-1)
    
    Returns:
        tuple: (ri_eligible, savings_plan_only)
    """
    ri_eligible = set()
    savings_plan_only = set()
    all_instances = set()
    
    # Map region code to the AWS price list "location" string
    region_to_location = {
        'us-east-1': 'US East (N. Virginia)'
    }
    location = region_to_location.get(region)
    
    # Process products
    products = price_list_data.get('products', {})
    for product_id, product in products.items():
        # Check if it's an EC2 instance in the specified region
        if (product.get('productFamily') == 'Compute Instance' and
            product.get('attributes', {}).get('location') == location):
            
            instance_type = product.get('attributes', {}).get('instanceType')
            if instance_type:
                all_instances.add(instance_type)
    
    # Process terms to determine pricing options
    terms = price_list_data.get('terms', {})
    
    # Check for Reserved Instance terms
    ri_terms = terms.get('Reserved', {})
    for term_id, term_details in ri_terms.items():
        sku = term_details.get('sku')
        for product_id, product in products.items():
            if product.get('sku') == sku and product.get('attributes', {}).get('location') == location:
                instance_type = product.get('attributes', {}).get('instanceType')
                if instance_type:
                    ri_eligible.add(instance_type)
    
    # Check for Savings Plan terms
    sp_terms = terms.get('SavingsPlan', {})
    for term_id, term_details in sp_terms.items():
        sku = term_details.get('sku')
        for product_id, product in products.items():
            if product.get('sku') == sku and product.get('attributes', {}).get('location') == location:
                instance_type = product.get('attributes', {}).get('instanceType')
                if instance_type:
                    # If instance has SP but not RI, add to savings_plan_only
                    if instance_type not in ri_eligible:
                        savings_plan_only.add(instance_type)
    
    # Convert sets to sorted lists for better readability
    return sorted(list(ri_eligible)), sorted(list(savings_plan_only))

def main():
    # Define dates to query - use past dates
    today = datetime.now()
    dates_to_query = [
        today - timedelta(days=1),  # Yesterday
        today - timedelta(days=30),  # 30 days ago
        today - timedelta(days=90),  # 90 days ago
        today - timedelta(days=180), # 180 days ago
        today - timedelta(days=365)  # 365 days ago
    ]
    
    results = []
    
    for date in dates_to_query:
        date_str = date.strftime('%Y-%m-%d')
        print(f"Finding price lists for {date_str}...")
        
        # Find available price lists
        price_lists = list_available_price_lists(date=date, currency_code='USD')
        print(json.dumps(price_lists, indent=3))
        if not price_lists:
            print(f"No price lists found for {date_str}")
            continue
        
        print(f"Found {len(price_lists)} price lists. Downloading the most recent one...")
        
        # Sort by effective date (newest first) and take the first one
        price_lists.sort(key=lambda x: x.get('PriceListArn', ''), reverse=True)
        selected_price_list = price_lists[0]
        
        priceListArn = selected_price_list.get('PriceListArn')
        if not priceListArn:
            print(f"No PriceListArn found for {date_str}")
            continue
            
        print(f"Price List ARN: {priceListArn}")

        # Extract the timestamp from the ARN
        # Format: arn:aws:pricing:::price-list/aws/AmazonEC2/USD/20250408165718/us-east-1
        match = re.search(r'/(\d{14})/', priceListArn)
        if not match:
            print(f"Could not extract timestamp from PriceListArn: {priceListArn}")
            continue
            
        timestamp = match.group(1)
        effective_date = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"

        # Need to use the ARN to get the price list using the get_price_list_file_url 
        client = boto3.client('pricing', region_name='us-east-1')
        response = client.get_price_list_file_url(
            PriceListArn=priceListArn,
            FileFormat='JSON'
        )
        print(json.dumps(response, indent=3))
        price_list_url = response.get('Url')
        print(f"Price List URL: {price_list_url}")

        if not price_list_url:
            print(f"No URL found for the selected price list on {date_str}")
            continue
            
        print(f"Downloading price list from: {price_list_url}")
        try:
            price_list_data = download_price_list(price_list_url)
        except Exception as e:
            print(f"Error downloading price list: {e}")
            continue
        

    #     # Analyze pricing options
    #     ri_eligible, savings_plan_only = analyze_ec2_pricing_options(price_list_data)
        
    #     # Save results
    #     results.append({
    #         'date': effective_date,
    #         'ri_eligible_count': len(ri_eligible),
    #         'savings_plan_only_count': len(savings_plan_only),
    #         'ri_eligible': ri_eligible,
    #         'savings_plan_only': savings_plan_only,
    #         'price_list_url': price_list_url
    #     })
        
    #     print(f"Found {len(ri_eligible)} RI-eligible instances and {len(savings_plan_only)} Savings Plan only instances.")
        
    #     # Save price list data for reference
    #     os.makedirs('price_lists', exist_ok=True)
    #     with open(f"price_lists/price_list_{effective_date.replace('-', '_')}.json", 'w') as f:
    #         json.dump(price_list_data, f, indent=2)
    
    # # Create DataFrame for easier analysis
    # if results:
    #     df = pd.DataFrame(results)
        
    #     # Save summary to CSV
    #     df[['date', 'ri_eligible_count', 'savings_plan_only_count', 'price_list_url']].to_csv('aws_pricing_analysis_summary.csv', index=False)
        
    #     # Save detailed instance lists
    #     for result in results:
    #         date_str = result['date'].replace('-', '_')
            
    #         with open(f"ri_eligible_{date_str}.json", 'w') as f:
    #             json.dump(result['ri_eligible'], f, indent=2, sort_keys=True)
            
    #         with open(f"savings_plan_only_{date_str}.json", 'w') as f:
    #             json.dump(result['savings_plan_only'], f, indent=2, sort_keys=True)
        
    #     print("Analysis complete. Results saved to CSV and JSON files.")
    # else:
    #     print("No results to analyze.")

if __name__ == "__main__":
    main()