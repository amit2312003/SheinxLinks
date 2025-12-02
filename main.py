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
    return "I am alive! Bot is running."

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# PART 2: BOT CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8297796693:AAHuho4cbyVNnCWwFZUQsna8RWcqor6mQZQ")
TELEGRAM_GROUP_ID = os.environ.get("TELEGRAM_GROUP", "-1003489527370")
TARGET_URL = "https://www.sheinindia.in/c/sverse-5939-37961"
CHECK_INTERVAL = 10 
SCROLL_DEPTH = 2

# ================= TELEGRAM SENDER =================
def send_alert(item):
    current_time = datetime.datetime.now().strftime("%I:%M:%S %p")
    stock_text = ""
    if item['sizes']:
        stock_text = "✏️ <b>Stock Status:</b>\n<pre>" + "\n".join(item['sizes']) + "</pre>\n"
    elif item['qty_msg']:
        stock_text = f"🔥 <b>Hurry:</b> ⚠️ {item['qty_msg']}\n"
    else:
        stock_text = "✏️ <b>Stock:</b> <i>Check Link</i>\n"

    caption = (
        f"⚡ <b>SHEINVERSE MEN'S UPDATE</b> ⚡\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"👔 <b>Product:</b>\n{item['title']}\n\n"
        f"💸 <b>Price:</b> {item['price']}\n"
        f"{stock_text}"
        f"🔗 <a href='{item['link']}'><b>CLICK To BUY</b></a>\n"
        f"🕒 <i>{current_time}</i>"
    )

    payload = {"chat_id": TELEGRAM_GROUP_ID, "caption": caption, "parse_mode": "HTML"}
    if item['img']:
        try:
            payload['photo'] = item['img']
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto", data=payload, timeout=10)
            return
        except: pass
    payload.pop('photo', None)
    payload['text'] = caption
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", data=payload, timeout=10)

# ================= DRIVER SETUP (SYSTEM CHROMIUM) =================
def get_driver():
    options = webdriver.ChromeOptions()
    # 🔴 THIS IS THE IMPORTANT PART THAT FIXES YOUR ERROR 🔴
    options.binary_location = "/usr/bin/chromium" 
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Use system installed driver
    service = Service("/usr/bin/chromedriver")
    return webdriver.Chrome(service=service, options=options)

# ================= STOCK CHECKER =================
def check_stock_details(driver, url):
    stock_info = []
    global_qty = ""
    original_window = driver.current_window_handle
    try:
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        driver.get(url)
        try:
            WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            if "only" in body_text and "left" in body_text: global_qty = "Low Stock"
        except: pass
        try:
            candidates = driver.find_elements(By.CSS_SELECTOR, "div.product-intro__size-radio, button")
            valid_labels = ['S', 'M', 'L', 'XL', 'XXL', '28', '30', '32', '34', '36']
            seen_sizes = set()
            for btn in candidates:
                txt = btn.text.strip().upper()
                if txt in valid_labels and txt not in seen_sizes:
                    status = "✅"
                    classes = (btn.get_attribute("class") or "")
                    if "disabled" in classes or "out" in classes: status = "❌"
                    stock_info.append(f"{txt}: {status}")
                    seen_sizes.add(txt)
                    if len(stock_info) >= 6: break
        except: pass
    except: pass
    finally:
        try:
            driver.close()
            driver.switch_to.window(original_window)
        except: pass
    return stock_info, global_qty

# ================= MAIN BOT LOOP =================
def run_bot():
    print("🚀 Men's Bot Started (System Chromium)...")
    seen = []
    driver = None
    while True:
        try:
            if driver is None:
                driver = get_driver()
                print("✅ Driver started.")
            
            driver.get(TARGET_URL)
            for _ in range(SCROLL_DEPTH):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            all_links = soup.find_all('a', href=True)
            new_count = 0
            
            for link in all_links:
                href = link['href']
                if ('-p-' in href or '/p/' in href) and len(link.get_text(strip=True)) > 2:
                    if not href.startswith('http'): full_link = "https://www.sheinindia.in" + href
                    else: full_link = href
                    try: p_id = full_link.split('/')[-1].split('.html')[0].split('-p-')[-1]
                    except: p_id = str(hash(full_link))
                    if p_id in seen: continue
                    
                    title = link.get_text(strip=True)
                    t_lower = title.lower()
                    if any(x in t_lower for x in ['women', 'girl', 'lady', 'dress', 'skirt']): continue
                    is_men = False
                    if 'men' in t_lower or 'man' in t_lower: is_men = True
                    elif any(x in t_lower for x in ['shirt', 'tee', 'pant', 'jeans', 'cargo']): is_men = True
                    if not is_men: continue

                    price = "Check Link"
                    container = link.parent
                    for _ in range(5):
                        if not container: break
                        found = container.find(string=lambda x: x and '₹' in x)
                        if found: 
                            price = found.strip()
                            break
                        container = container.parent
                    
                    img_url = ""
                    try:
                        img = link.find('img') or link.parent.find('img')
                        if img: 
                            img_url = img.get('data-src') or img.get('src')
                            if img_url and not img_url.startswith('http'): img_url = "https:" + img_url
                    except: pass
                    
                    sizes, qty = check_stock_details(driver, full_link)
                    send_alert({"title": title, "price": price, "link": full_link, "img": img_url, "sizes": sizes, "qty_msg": qty})
                    seen.append(p_id)
                    new_count += 1
            
            if len(seen) > 200: seen = seen[-100:]
            if new_count > 0: print(f"Sent {new_count} updates.")
            else: print(".", end="", flush=True)

        except Exception as e:
            print(f"Error: {e}")
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
