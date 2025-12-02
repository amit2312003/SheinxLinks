import os
import time
import json
import requests
import datetime
import threading
from flask import Flask
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ==========================================
# PART 1: FAKE WEB SERVER
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Shein Men's State-Tracker Bot Running."

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# PART 2: CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8297796693:AAHuho4cbyVNnCWwFZUQsna8RWcqor6mQZQ")
TELEGRAM_GROUP_ID = os.environ.get("TELEGRAM_GROUP", "-1003489527370")

# 🔗 NEW LINK (Pre-filtered for Men)
TARGET_URL = "https://www.sheinindia.in/c/sverse-5939-37961?query=%3Arelevance%3Agenderfilter%3AMen"

CHECK_INTERVAL = 5 
SCROLL_DEPTH = 3

# ================= TELEGRAM SENDER =================
def send_alert(item, alert_type):
    current_time = datetime.datetime.now().strftime("%I:%M:%S %p")
    
    # Custom Headers based on the State Change
    if alert_type == "NEW":
        header = "✨ <b>NEW MEN'S DROP</b> ✨"
    elif alert_type == "RESTOCK":
        header = "🔄 <b>BACK IN STOCK</b> 🔄"
    elif alert_type == "SOLD_OUT":
        header = "❌ <b>SOLD OUT</b> ❌"
    else:
        header = "⚡ <b>SHEINVERSE UPDATE</b>"

    # Stock Text Formatting
    stock_text = ""
    if alert_type == "SOLD_OUT":
        stock_text = "🚫 <b>Status:</b> Currently Out of Stock\n"
    else:
        if item['sizes']:
            stock_text = "📏 <b>Sizes Available:</b>\n<pre>"
            for s in item['sizes']:
                stock_text += f"{s}\n"
            stock_text += "</pre>\n"
        elif item['qty_msg']:
            stock_text = f"🔥 <b>Hurry:</b> {item['qty_msg']}\n"
        else:
            stock_text = "✅ <b>Status:</b> In Stock\n"

    caption = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"👔 <b>Product:</b>\n{item['title']}\n\n"
        f"💸 <b>Price:</b> {item['price']}\n"
        f"{stock_text}"
        f"🔗 <a href='{item['link']}'><b>CLICK TO VIEW</b></a>\n"
        f"🕒 <i>{current_time}</i>\n\n"
        f"🤖 <b>Developed by - @OfficialToonsworld</b>"
    )

    payload = {"chat_id": TELEGRAM_GROUP_ID, "caption": caption, "parse_mode": "HTML"}
    
    # Only send photo for In Stock items (User usually doesn't need photo for OOS alert, but we can keep it)
    if item['img']:
        try:
            payload['photo'] = item['img']
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto", data=payload, timeout=10)
            return
        except: pass
        
    payload.pop('photo', None)
    payload['text'] = caption
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", data=payload, timeout=10)

# ================= DRIVER SETUP =================
def get_driver():
    options = webdriver.ChromeOptions()
    options.binary_location = "/usr/bin/chromium"
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    service = Service("/usr/bin/chromedriver")
    return webdriver.Chrome(service=service, options=options)

# ================= STOCK CHECKER =================
def check_stock_details(driver, url):
    stock_info = []
    global_qty = ""
    is_fully_oos = True # Default to OOS until we find stock
    
    original_window = driver.current_window_handle
    try:
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        driver.get(url)
        
        # 1. Global "Only X Left" check
        try:
            WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            if "hurry" in body_text and "left" in body_text:
                lines = body_text.split('\n')
                for line in lines:
                    if "only" in line and "left" in line:
                        global_qty = line.strip().title()
                        break
        except: pass

        # 2. Detailed Size Check
        try:
            candidates = driver.find_elements(By.CSS_SELECTOR, "div.product-intro__size-radio, button, div.goods-size__radio")
            valid_labels = ['XS', 'S', 'M', 'L', 'XL', 'XXL', '3XL', '28', '30', '32', '34', '36', '38', '40', '42']
            seen_sizes = set()

            for btn in candidates:
                txt = btn.text.strip().upper().split('\n')[0].strip()

                if txt in valid_labels and txt not in seen_sizes:
                    classes = (btn.get_attribute("class") or "")
                    
                    # Logic: If NOT disabled, it is IN STOCK
                    if "disabled" in classes or "out" in classes or "attr-radio-disabled" in classes:
                        stock_info.append(f"{txt.ljust(4)} : ❌")
                    else:
                        stock_info.append(f"{txt.ljust(4)} : ✅")
                        is_fully_oos = False # Found at least one size!

                    seen_sizes.add(txt)
        except: pass

    except: pass
    finally:
        try:
            driver.close()
            driver.switch_to.window(original_window)
        except: pass

    # If no sizes found at all, assume OOS
    if not stock_info and not global_qty:
        is_fully_oos = True

    return stock_info, global_qty, is_fully_oos

# ================= MAIN BOT LOOP =================
def run_bot():
    print("🚀 State-Tracking Bot Started...")
    
    # MEMORY: { "product_id": True/False } 
    # True = In Stock, False = Out of Stock
    product_states = {} 

    driver = None

    while True:
        try:
            if driver is None:
                driver = get_driver()
            
            driver.get(TARGET_URL)
            for _ in range(SCROLL_DEPTH):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            all_links = soup.find_all('a', href=True)
            
            for link in all_links:
                href = link['href']
                if ('-p-' in href or '/p/' in href) and len(link.get_text(strip=True)) > 2:
                    if not href.startswith('http'): full_link = "https://www.sheinindia.in" + href
                    else: full_link = href

                    try: p_id = full_link.split('/')[-1].split('.html')[0].split('-p-')[-1]
                    except: p_id = str(hash(full_link))

                    title = link.get_text(strip=True)

                    # Get Price
                    price = "Check Link"
                    container = link.parent
                    for _ in range(5):
                        if not container: break
                        found = container.find(string=lambda x: x and '₹' in x)
                        if found: 
                            price = found.strip()
                            break
                        container = container.parent
                    
                    # Get Image
                    img_url = ""
                    try:
                        img = link.find('img') or link.parent.find('img')
                        if img: 
                            img_url = img.get('data-src') or img.get('src')
                            if img_url and not img_url.startswith('http'): img_url = "https:" + img_url
                    except: pass
                    
                    # === STOCK CHECK ===
                    sizes, qty, is_oos = check_stock_details(driver, full_link)
                    is_in_stock = not is_oos # Helper boolean
                    
                    # === STATE MACHINE LOGIC ===
                    
                    # Scenario 1: First time seeing this product
                    if p_id not in product_states:
                        if is_in_stock:
                            # It's New AND In Stock -> SEND
                            send_alert({
                                "title": title, "price": price, "link": full_link, 
                                "img": img_url, "sizes": sizes, "qty_msg": qty
                            }, "NEW")
                            product_states[p_id] = True # Mark as In Stock
                        else:
                            # It's New but OOS -> IGNORE (Per user request)
                            # We still track it so if it comes in stock later, we know.
                            product_states[p_id] = False 
                            
                    # Scenario 2: We have seen this product before
                    else:
                        was_in_stock = product_states[p_id]
                        
                        # Case A: Was In Stock -> Now OOS
                        if was_in_stock and not is_in_stock:
                            send_alert({
                                "title": title, "price": price, "link": full_link, 
                                "img": img_url, "sizes": [], "qty_msg": ""
                            }, "SOLD_OUT")
                            product_states[p_id] = False # Update state
                            
                        # Case B: Was OOS -> Now In Stock
                        elif not was_in_stock and is_in_stock:
                            send_alert({
                                "title": title, "price": price, "link": full_link, 
                                "img": img_url, "sizes": sizes, "qty_msg": qty
                            }, "RESTOCK")
                            product_states[p_id] = True # Update state
                            
                        # Case C: Status didn't change (True->True or False->False) -> DO NOTHING

        except Exception as e:
            print(f"Loop Error: {e}")
            try: 
                if driver: driver.quit()
            except: pass
            driver = None 
            
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    t = threading.Thread(target=run_web_server)
    t.daemon = True
    t.start()
    run_bot()
