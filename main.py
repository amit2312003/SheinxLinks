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
# PART 1: FAKE WEB SERVER (Keep Render Awake)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running! checking Men's Sheinverse."

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# ==========================================
# PART 2: BOT CONFIGURATION
# ==========================================
# 🔑 SECURITY: Get tokens from Environment or use defaults
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8297796693:AAHuho4cbyVNnCWwFZUQsna8RWcqor6mQZQ")
TELEGRAM_GROUP_ID = os.environ.get("TELEGRAM_GROUP", "-1003489527370")

# 🔗 TARGET: Sheinverse All Items (We filter for Men later)
TARGET_URL = "https://www.sheinindia.in/c/sverse-5939-37961"

# ⏱️ SPEED: Check every 5 seconds
CHECK_INTERVAL = 5 
SCROLL_DEPTH = 3

# ================= TELEGRAM SENDER =================
def send_alert(item):
    current_time = datetime.datetime.now().strftime("%I:%M:%S %p")
    
    # 1. Determine Overall Header (Green or Red)
    header_status = "🟢 IN STOCK"
    if item['is_oos']:
        header_status = "🔴 OUT OF STOCK"
    elif item['qty_msg'] and "only" in item['qty_msg'].lower():
        header_status = "🟠 LOW STOCK"

    # 2. Format Size List
    stock_text = ""
    if item['sizes']:
        stock_text = "📏 <b>Sizes:</b>\n<pre>"
        for s in item['sizes']:
            # Example: "M : ✅" or "L : ❌"
            stock_text += f"{s}\n"
        stock_text += "</pre>\n"
    elif item['is_oos']:
        stock_text = "📏 <b>Sizes:</b> ❌ None Available\n"
    else:
        stock_text = "📏 <b>Sizes:</b> <i>Check Link</i>\n"

    # 3. Quantity Message
    qty_text = ""
    if item['qty_msg']:
        qty_text = f"📦 <b>Quantity:</b> {item['qty_msg']}\n"

    caption = (
        f"{header_status} ⚡ <b>SHEINVERSE MEN</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n\n"
        f"👔 <b>Product:</b>\n{item['title']}\n\n"
        f"💸 <b>Price:</b> {item['price']}\n"
        f"{qty_text}"
        f"{stock_text}"
        f"🔗 <a href='{item['link']}'><b>CLICK TO VIEW</b></a>\n"
        f"🕒 <i>{current_time}</i>"
    )

    payload = {"chat_id": TELEGRAM_GROUP_ID, "caption": caption, "parse_mode": "HTML"}
    
    # Try sending with image, fallback to text
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
    options.binary_location = "/usr/bin/chromium"  # 👈 CRITICAL FOR RENDER
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    service = Service("/usr/bin/chromedriver") # 👈 CRITICAL FOR RENDER
    return webdriver.Chrome(service=service, options=options)

# ================= STOCK CHECKER (DETAILED) =================
def check_stock_details(driver, url):
    stock_info = []
    global_qty = ""
    is_fully_oos = True # Assume OOS until we find a button
    
    original_window = driver.current_window_handle
    try:
        # Open new tab for details
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        driver.get(url)
        
        # 1. Check for "Only X Left" text
        try:
            WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            if "hurry" in body_text and "left" in body_text:
                # Try to extract the specific line
                lines = body_text.split('\n')
                for line in lines:
                    if "only" in line and "left" in line:
                        global_qty = line.strip().title() # e.g. "Only 5 Left"
                        break
        except: pass

        # 2. Check Size Buttons
        try:
            # Common selectors for size buttons
            candidates = driver.find_elements(By.CSS_SELECTOR, "div.product-intro__size-radio, button, div.goods-size__radio")
            valid_labels = ['XS', 'S', 'M', 'L', 'XL', 'XXL', '3XL', '28', '30', '32', '34', '36', '38', '40', '42']
            seen_sizes = set()

            for btn in candidates:
                txt = btn.text.strip().upper()
                # Clean up text (sometimes contains price or extra spaces)
                txt = txt.split('\n')[0].strip()

                if txt in valid_labels and txt not in seen_sizes:
                    classes = (btn.get_attribute("class") or "")
                    
                    status_icon = "✅"
                    # If class contains disabled/out/sold-out
                    if "disabled" in classes or "out" in classes or "attr-radio-disabled" in classes:
                        status_icon = "❌"
                    else:
                        is_fully_oos = False # Found at least one stock item!

                    stock_info.append(f"{txt.ljust(4)} : {status_icon}")
                    seen_sizes.add(txt)
        except: pass

    except Exception as e:
        print(f"Stock Check Error: {e}")
    finally:
        try:
            driver.close()
            driver.switch_to.window(original_window)
        except: pass

    return stock_info, global_qty, is_fully_oos

# ================= MAIN BOT LOOP =================
def run_bot():
    print("🚀 Men's Bot Started (Every 5s - All Stock Status)...")
    seen = []
    driver = None

    while True:
        try:
            if driver is None:
                driver = get_driver()
                print("✅ Driver started.")

            driver.get(TARGET_URL)
            
            # Scroll to load items
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

                    # ==========================================
                    # 🛡️ STRICT MEN'S FILTER
                    # ==========================================
                    # 1. Reject Women's keywords immediately
                    if any(x in t_lower for x in ['women', 'girl', 'lady', 'dress', 'skirt', 'bikini', 'heels']): 
                        continue

                    # 2. Check for Men's keywords OR Neutral categories
                    is_men = False
                    if 'men' in t_lower or 'man' in t_lower: 
                        is_men = True
                    elif any(x in t_lower for x in ['shirt', 'tee', 'pant', 'jeans', 'cargo', 'hoodie', 'trouser', 'short']): 
                        # If it has these words AND passed the rejection above, it's likely Men's
                        is_men = True
                    
                    if not is_men: continue
                    # ==========================================

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
                    
                    # CHECK STOCK (Even if OOS)
                    sizes, qty, is_oos = check_stock_details(driver, full_link)
                    
                    # Send Alert
                    send_alert({
                        "title": title, 
                        "price": price, 
                        "link": full_link, 
                        "img": img_url, 
                        "sizes": sizes, 
                        "qty_msg": qty,
                        "is_oos": is_oos
                    })

                    seen.append(p_id)
                    new_count += 1
            
            # Keep seen list manageable
            if len(seen) > 300: seen = seen[-150:]
            
            if new_count > 0: print(f"Sent {new_count} updates.")
            else: print(".", end="", flush=True)

        except Exception as e:
            print(f"Loop Error: {e}")
            try: 
                if driver: driver.quit()
            except: pass
            driver = None # Restart driver on next loop
            
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    t = threading.Thread(target=run_web_server)
    t.daemon = True
    t.start()
    run_bot()
