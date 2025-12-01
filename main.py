import os
import json
import time
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    print(f"Loaded .env from {dotenv_path}")
else:
    print("Warning: .env file not found.")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("Error: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not found in environment variables.")


# Target URLs
# Commenting out 404/403 sites for now to focus on working ones, but keeping the logic ready.
URLS = [
    # "https://kruti.com.ua/ua/pokryshka-schwalbe-smart-sam-29x2.35/", # 404
    "https://rozetka.com.ua/ua/schwalbe-tir-61-47/p426701688/",
    # "https://veliki.ua/pokryshka-29-smart-sam/", # 403
    "https://veloplaneta.ua/ua/pokryshka-29x2-35-60-622-schwalbe-smart-sam-perf-b-brz-sk-hs624-addix-67epi",
    # "https://velosiped.com/katalog/shiny/schwalbe/smart-sam-29.html", # 404
    # "https://velopuls.ua/schwalbe-smart-sam-29.html" # 404
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7"
}

def send_telegram_message(message):
    """Sends a message to the Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def get_html(url):
    """Fetches HTML content with error handling."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return response.text
    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP Error {e.response.status_code}"
        print(f"Error fetching {url}: {error_msg}")
        send_telegram_message(f"⚠️ <b>Error Parsing Site</b>\nURL: {url}\nType: HTTP Error\nText: {error_msg}")
        return None
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        send_telegram_message(f"⚠️ <b>Error Parsing Site</b>\nURL: {url}\nType: Exception\nText: {str(e)}")
        return None

def extract_price(soup, specific_selector=None):
    """Helper to extract price digits."""
    price_text = ""
    if specific_selector:
        el = soup.select_one(specific_selector)
        if el:
            price_text = el.text
    
    if not price_text:
        # Fallback: look for currency
        el = soup.find(string=lambda t: t and ('грн' in t.lower() or '₴' in t))
        if el:
            price_text = el.parent.text if el.parent else el

    # Clean up
    digits = "".join(filter(str.isdigit, price_text))
    return digits if digits else "N/A"

def parse_rozetka(html, url):
    soup = BeautifulSoup(html, 'lxml')
    try:
        title_el = soup.select_one('h1')
        title = title_el.text.strip() if title_el else "Unknown Product"
        
        price = extract_price(soup, '.product-prices__big')
        
        stock = "In Stock"
        if soup.select_one('.status-label--unavailable'):
            stock = "Out of Stock"
            
        return {"name": title, "price": price, "stock": stock, "url": url}
    except Exception as e:
        print(f"Error parsing Rozetka: {e}")
        return None

def parse_veloplaneta(html, url):
    soup = BeautifulSoup(html, 'lxml')
    try:
        title_el = soup.select_one('h1')
        title = title_el.text.strip() if title_el else "Unknown Product"
        
        # Veloplaneta usually has price in .price or .product-price
        price = extract_price(soup, '.price')
        
        stock = "In Stock"
        # Logic to check stock if specific class exists
        if "немає в наявності" in html.lower():
             stock = "Out of Stock"

        return {"name": title, "price": price, "stock": stock, "url": url}
    except Exception as e:
        print(f"Error parsing Veloplaneta: {e}")
        return None

def main():
    results = []
    print(f"Starting scrape for {len(URLS)} URLs...")
    
    for url in URLS:
        print(f"Processing {url}...")
        html = get_html(url)
        if not html:
            continue
        
        data = None
        if "rozetka.com.ua" in url:
            data = parse_rozetka(html, url)
        elif "veloplaneta.ua" in url:
            data = parse_veloplaneta(html, url)
        
        if data:
            results.append(data)
            print(f"Found: {data['name']} - {data['price']} UAH")
        else:
            print(f"Failed to parse data for {url}")
        
        time.sleep(2) # Be polite

    if results:
        msg = "<b>Schwalbe Price Monitor Report</b>\n\n"
        for item in results:
            msg += f"{item['name']}\n💰 <b>{item['price']} UAH</b> | {item['stock']}\n<a href='{item['url']}'>Link</a>\n\n"
        
        print("Sending Telegram report...")
        send_telegram_message(msg)
        
        # Save to JSON
        with open('prices.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print("Done.")
    else:
        print("No results found.")

if __name__ == "__main__":
    main()
