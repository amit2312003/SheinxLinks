import os
import time
import json
import requests
import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ==========================================
# CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = "8297796693:AAHuho4cbyVNnCWwFZUQsna8RWcqor6mQZQ"
TELEGRAM_GROUP_ID = "-1003489527370"
# Ensure this is the correct Sheinverse Link. 
# If you want specific categories, change this URL.
TARGET_URL = "https://www.sheinindia.in/c/sverse-5939-37961"

CHECK_INTERVAL = 5      # Checks every 5 seconds (Fastest safe speed)
SCROLL_DEPTH = 2        # Reduced to 2 for speed (New items are usually at the top)

POST_COUNT = 0
SEEN_FILE = "seen.json"

# ================= TELEGRAM SENDER =================
def send_alert(item):
    global POST_COUNT
    POST_COUNT += 1
    current_time = datetime.datetime.now().strftime("%I:%M:%S %p")

    # Stock formatting
    stock_text = ""
    if item['sizes']:
        stock_text = "✏️ <b>Stock Status:</b>\n<pre>"
        for s in item['sizes']:
            stock_text += f"{s}\n"
        stock_text += "</pre>\n"
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
        f"🕒 <i>{current_time}</i>\n\n"
        f"🤖 <b>Developed by join @officialtoonsworld</b>"
    )

    payload = {
        "chat_id": TELEGRAM_GROUP_ID, 
        "caption": caption, 
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    # Attempt to send photo
    if item['img']:
        try:
            payload['photo'] = item['img']
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto", data=payload, timeout=10)
            print(f"💌 Sent: {item['title'][:20]}...")
            return
        except Exception as e:
            print(f"⚠️ Photo failed, sending text: {e}")

    # Fallback to text
    payload.pop('photo', None)
    payload['text'] = caption
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", data=payload, timeout=10)

# ================= DRIVER SETUP (DOCKER OPTIMIZED) =================
def get_driver():
    options = webdriver.ChromeOptions()
    # These options are mandatory for Docker/Railway
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Use webdriver_manager to handle the driver binary automatically
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

# ================= STOCK CHECKER =================
def check_stock_details(driver, url):
    stock_info = []
    global_qty = ""
    
    # We open a new tab to check stock to keep the main flow separate
    original_window = driver.current_window_handle
    try:
        driver.execute_script("window.open('');")
        driver.switch_to.window(driver.window_handles[-1])
        driver.get(url)

        # 1. Quick Scan for "Only X Left" text
        try:
            WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            if "only" in body_text and "left" in body_text:
                global_qty = "Low Stock / Fast Selling"
        except: pass

        # 2. Check Size Buttons
        try:
            # Look for size buttons
            candidates = driver.find_elements(By.CSS_SELECTOR, "div.product-intro__size-radio, button, span")
            valid_labels = ['XS', 'S', 'M', 'L', 'XL', 'XXL', '28', '30', '32', '34', '36', '38', '40']
            seen_sizes = set()

            for btn in candidates:
                txt = btn.text.strip().upper()
                if txt in valid_labels and txt not in seen_sizes:
                    classes = (btn.get_attribute("class") or "") + (btn.get_attribute("title") or "")
                    
                    icon = "✅"
                    status = "In Stock"
                    
                    if "disabled" in classes or "out" in classes or "grey" in classes:
                        icon = "❌"
                        status = "Out"
                    
                    stock_info.append(f"{txt.ljust(4)} : {icon} {status}")
                    seen_sizes.add(txt)
                    if len(stock_info) >= 6: break # Limit info
        except: pass

    except Exception as e:
        print(f"Stock check warning: {e}")
    finally:
        # Close the tab and go back
        try:
            driver.close()
            driver.switch_to.window(original_window)
        except: pass

    return stock_info, global_qty

# ================= MAIN LOOP =================
if __name__ == "__main__":
    print("🚀 Men's Bot Started on Cloud...")

    # Load seen products
    seen = []
    # Note: On Railway, this file resets when the bot restarts.
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f: seen = json.load(f)
        except: pass

    driver = get_driver()
    print("✅ Chrome Driver Active.")

    while True:
        try:
            driver.get(TARGET_URL)
            
            # Fast Scroll
            for _ in range(SCROLL_DEPTH):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            # Finding all product links
            all_links = soup.find_all('a', href=True)
            
            new_found = 0

            for link in all_links:
                href = link['href']
                
                # Filter for valid product links
                if ('-p-' in href or '/p/' in href) and len(link.get_text(strip=True)) > 2:
                    
                    # Construct full URL
                    if not href.startswith('http'): full_link = "https://www.sheinindia.in" + href
                    else: full_link = href

                    # Extract ID
                    try:
                        p_id = full_link.split('/')[-1].split('.html')[0].split('-p-')[-1]
                    except: p_id = str(hash(full_link))

                    if p_id in seen: continue

                    title = link.get_text(strip=True)
                    t_lower = title.lower()

                    # ==========================================
                    # 🛡️ MEN'S FILTER LOGIC
                    # ==========================================
                    # 1. Immediate rejection of Women/Kids keywords
                    if any(x in t_lower for x in ['women', 'girl', 'lady', 'dress', 'skirt', 'bikini']):
                        continue

                    # 2. Acceptance Logic
                    is_men = False
                    
                    # Direct Keyword Check
                    if 'men' in t_lower or 'man' in t_lower or 'male' in t_lower:
                        is_men = True
                    # Category Check (Shirt, T-shirt, Jeans, Cargo often implies Unisex/Men if not labeled Women)
                    elif any(x in t_lower for x in ['shirt', 'tee', 'pant', 'jeans', 'cargo', 'hoodie', 'trouser']):
                        # Double check it doesn't say "Women" (already filtered above, but safety check)
                        is_men = True

                    if not is_men: continue

                    # ==========================================
                    # SCRAPE DETAILS
                    # ==========================================
                    # Find price
                    container = link.parent
                    price = "Check Link"
                    # bubble up to find price
                    for _ in range(5):
                        if not container: break
                        found_price = container.find(string=lambda x: x and '₹' in x)
                        if found_price:
                            price = found_price.strip()
                            break
                        container = container.parent
                    
                    # Find Image
                    img_url = ""
                    try:
                        img_tag = link.find('img') or link.parent.find('img') or link.parent.parent.find('img')
                        if img_tag:
                            img_url = img_tag.get('data-src') or img_tag.get('src') or ""
                            if img_url and not img_url.startswith('http'): img_url = "https:" + img_url
                    except: pass

                    # Check Stock Details
                    sizes, qty_msg = check_stock_details(driver, full_link)

                    send_alert({
                        "title": title,
                        "price": price,
                        "link": full_link,
                        "img": img_url,
                        "sizes": sizes,
                        "qty_msg": qty_msg
                    })

                    seen.append(p_id)
                    new_found += 1
            
            # Save seen list (Note: Temporary on some cloud hosts)
            if new_found > 0:
                with open(SEEN_FILE, "w") as f: json.dump(seen, f)
                print(f"✅ Posted {new_found} items.")
            else:
                print(".", end="", flush=True)

        except Exception as e:
            print(f"❌ Error in loop: {e}")
            # Restart driver if it crashes
            try:
                driver.quit()
                driver = get_driver()
            except: pass
            
        time.sleep(CHECK_INTERVAL)
