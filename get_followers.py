import os
import time
import pickle
import sys
import re
from collections import deque
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

COOKIES_FILE = "cookies.pkl"
CREDENTIALS_FILE = "credentials.txt"
PROFILE_DIR = os.path.abspath("chrome_profile")


def load_credentials():
    if not os.path.exists(CREDENTIALS_FILE):
        return None
    with open(CREDENTIALS_FILE, "r", encoding="utf-8") as file:
        lines = [line.strip() for line in file if line.strip()]
        if len(lines) >= 2:
            return lines[0], lines[1]
    return None


def get_stealth_driver(headless=False):
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.navigator.chrome = { runtime: {} };
        """
        },
    )
    return driver


def load_saved_cookies(driver):
    if os.path.exists(COOKIES_FILE):
        try:
            driver.get("https://www.instagram.com/")
            time.sleep(2)
            with open(COOKIES_FILE, "rb") as f:
                cookies = pickle.load(f)
                for cookie in cookies:
                    try:
                        driver.add_cookie(cookie)
                    except Exception:
                        pass
            driver.refresh()
            time.sleep(3)
            return True
        except Exception as e:
            print(f"[!] Error loading cookies: {e}")
    return False


def is_logged_in(driver):
    driver.get("https://www.instagram.com/")
    time.sleep(3)
    curr_url = driver.current_url.lower()
    if "login" not in curr_url and "auth_platform" not in curr_url:
        nav = driver.find_elements(By.CSS_SELECTOR, "svg[aria-label='Home'], svg[aria-label='Search'], nav")
        if nav:
            return True
    return False


def login_if_needed(driver):
    if is_logged_in(driver):
        return True

    if load_saved_cookies(driver) and is_logged_in(driver):
        return True

    creds = load_credentials()
    if not creds:
        print("[!] No credentials found in credentials.txt!")
        return False

    username, password = creds
    print(f"[+] Logging in as {username}...")
    driver.get("https://www.instagram.com/accounts/login/")
    time.sleep(4)

    try:
        u_in = driver.find_element(By.CSS_SELECTOR, "input[name='email'], input[name='username'], input[type='text']")
        p_in = driver.find_element(By.CSS_SELECTOR, "input[name='pass'], input[name='password'], input[type='password']")

        u_in.clear()
        for c in username:
            u_in.send_keys(c)
            time.sleep(0.02)

        p_in.clear()
        for c in password:
            p_in.send_keys(c)
            time.sleep(0.02)

        login_divs = driver.find_elements(By.XPATH, "//div[@role='button'][contains(., 'Log in')] | //button[contains(., 'Log in')]")
        if login_divs:
            driver.execute_script("arguments[0].click();", login_divs[0])
        else:
            p_in.send_keys(Keys.RETURN)

        time.sleep(8)
    except Exception as e:
        print(f"[!] Login error: {e}")

    if is_logged_in(driver):
        try:
            with open(COOKIES_FILE, "wb") as f:
                pickle.dump(driver.get_cookies(), f)
        except Exception:
            pass
        return True
    else:
        print("[!] Login failed or security check triggered. Please check the browser window.")
        return False


def extract_followers_from_profile(driver, username, max_per_user=50):
    print(f"[+] Navigating to profile: https://www.instagram.com/{username}/")
    driver.get(f"https://www.instagram.com/{username}/")
    # Increased profile load wait to 5 seconds
    time.sleep(5.0)

    page_text = driver.page_source.lower()
    # Check if account is private or unavailable
    if "this account is private" in page_text:
        print(f"[-] @{username} is private. Skipping and removing from output.")
        return [], True

    followers_links = driver.find_elements(By.XPATH, f"//a[contains(@href, '/followers/')] | //a[contains(@href, '/{username}/followers')]")
    if not followers_links:
        followers_links = driver.find_elements(By.XPATH, "//span[contains(text(), 'followers')]/ancestor::a | //a[contains(., 'followers')]")

    if not followers_links:
        print(f"[!] Followers link not found on @{username}'s profile.")
        return [], False

    try:
        followers_links[0].click()
        # Increased wait to 5 seconds after clicking followers link to allow modal to load
        print(f"[+] Followers link clicked for @{username}. Waiting 5s for followers modal...")
        time.sleep(5.0)
    except Exception:
        print(f"[!] Could not click followers link on @{username}.")
        return [], False

    try:
        modal = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
        )
    except Exception:
        print(f"[!] Followers modal did not open for @{username}.")
        return [], False

    time.sleep(2.0)

    scrollable_div = driver.execute_script("""
        const dialog = arguments[0];
        const divs = Array.from(dialog.querySelectorAll('div'));
        return divs.find(d => {
            const style = window.getComputedStyle(d);
            return style.overflowY === 'scroll' || style.overflowY === 'auto';
        }) || dialog;
    """, modal)

    # Scroll 10 times with 1.5s delay to trigger infinite scroll for all 50 items
    for _ in range(10):
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", scrollable_div)
        time.sleep(1.5)

    extracted = set()
    links = modal.find_elements(By.TAG_NAME, "a")
    for link in links:
        try:
            href = link.get_attribute("href")
            if href and "instagram.com/" in href:
                clean_path = href.split("instagram.com/")[-1].strip("/")
                parts = [p for p in clean_path.split("/") if p]
                if parts:
                    uname = parts[0]
                    if uname not in ["explore", "direct", "stories", "reels", username] and not uname.startswith("?") and not uname.startswith("#"):
                        extracted.add(uname)
                        if len(extracted) >= max_per_user:
                            break
        except Exception:
            pass

    return list(extracted), False


def fetch_followers_tree(target_username, target_count):
    driver = get_stealth_driver(headless=False)
    collected_followers = set()
    visited_accounts = set()

    # Queue stores tuple: (username, tree_level, parent_username)
    queue = deque([(target_username, 1, "ROOT")])

    try:
        if not login_if_needed(driver):
            print("[!] Cannot proceed without logged in session.")
            return []

        creds = load_credentials()
        my_username = creds[0].lower() if creds else ""

        print(f"\n[+] Starting Tree Crawler for target @{target_username} (Goal: {target_count} followers)...")

        node_counter = 0
        while queue and len(collected_followers) < target_count:
            current_user, level, parent = queue.popleft()
            uname_lower = current_user.lower()

            if uname_lower in visited_accounts or uname_lower == my_username:
                continue

            visited_accounts.add(uname_lower)
            node_counter += 1

            print(f"\n[Tree Level {level} | Node #{node_counter}] Processing @{current_user} (Parent: @{parent})")
            print(f"[+] Total Unique Followers Collected: {len(collected_followers)} / {target_count}")

            followers_batch, is_private = extract_followers_from_profile(driver, current_user, max_per_user=50)

            if is_private:
                if current_user in collected_followers:
                    collected_followers.remove(current_user)
                    print(f"[-] Removed private account @{current_user} from followers list.")
                continue

            added_count = 0
            for f in followers_batch:
                f_lower = f.lower()
                if f_lower not in collected_followers and f_lower != target_username.lower() and f_lower != my_username:
                    collected_followers.add(f)
                    added_count += 1
                    queue.append((f, level + 1, current_user))
                    if len(collected_followers) >= target_count:
                        break

            print(f"[+] Found {len(followers_batch)} followers from @{current_user}. Added {added_count} new unique accounts. Total: {len(collected_followers)} / {target_count}")

            time.sleep(1.5)

    finally:
        driver.quit()

    return list(collected_followers)[:target_count]


def main():
    print("=" * 60)
    print("      Instagram Tree Follower Collector - 2026        ")
    print("=" * 60)

    if len(sys.argv) >= 3:
        target_username = sys.argv[1].strip()
        try:
            max_count = int(sys.argv[2])
        except ValueError:
            max_count = 5000
    else:
        target_username = input("Enter target Instagram username (e.g. flstudio): ").strip()
        count_str = input("Enter number of followers to scrape (default 5000): ").strip()
        try:
            max_count = int(count_str) if count_str else 5000
        except ValueError:
            max_count = 5000

    if not target_username:
        print("[!] No username provided. Exiting.")
        return

    output_filename = f"{target_username}_followers_{max_count}.txt"
    print(f"\n[+] Target Account: {target_username}")
    print(f"[+] Target Follower Goal: {max_count}")
    print(f"[+] Output File: {output_filename}\n")

    followers = fetch_followers_tree(target_username, max_count)

    if followers:
        with open(output_filename, "w", encoding="utf-8") as f:
            for uname in followers:
                f.write(f"{uname}\n")
        print(f"\n[SUCCESS] Saved {len(followers)} unique followers to '{output_filename}'!")

        print(f"[+] Updating 'followers.txt' for Instagram Story Liker...")
        with open("followers.txt", "w", encoding="utf-8") as f:
            for uname in followers:
                f.write(f"{uname}\n")
        print(f"[+] 'followers.txt' updated with {len(followers)} followers!")
    else:
        print("[!] No followers retrieved.")


if __name__ == "__main__":
    main()
