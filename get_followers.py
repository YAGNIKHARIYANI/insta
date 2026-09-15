import os
import time
import pickle
import sys
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    NoSuchWindowException,
    WebDriverException,
)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

COOKIES_FILE = "cookies.pkl"
CREDENTIALS_FILE = "credentials.txt"
PROFILE_DIR = os.path.abspath("chrome_profile")
POST_LINKS_FILE = "post_links.txt"

SYSTEM_EXCLUDED_USERNAMES = {
    "explore", "direct", "stories", "reels", "p", "reel", "about", "privacy",
    "terms", "help", "api", "jobs", "locations", "threads", "muse", "meta",
    "meta_ai", "contact", "instagram_lite", "popular", "web", "blog", "legal",
    "accounts", "download", "press", "cookies"
}


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
    try:
        driver.get("https://www.instagram.com/")
        time.sleep(3)
        curr_url = driver.current_url.lower()
        if "login" not in curr_url and "auth_platform" not in curr_url:
            nav = driver.find_elements(By.CSS_SELECTOR, "svg[aria-label='Home'], svg[aria-label='Search'], nav")
            if nav:
                return True
    except Exception:
        pass
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


def scrape_commenters_from_post(driver, post_url, my_username=""):
    print(f"\n[+] Navigating to Post/Reel: {post_url}")
    try:
        driver.get(post_url)
        time.sleep(4.0)

        # Expand comments by clicking "View more comments", "Load more comments" or + buttons
        print("[+] Expanding comments on post...")
        for step in range(12):
            buttons = driver.find_elements(
                By.XPATH,
                "//button[contains(., 'View more comments')] | //button[contains(., 'Load more comments')] | //svg[@aria-label='Load more comments']/ancestor::button | //ul//button[.//svg]"
            )
            clicked = False
            for b in buttons:
                try:
                    if b.is_displayed():
                        driver.execute_script("arguments[0].click();", b)
                        clicked = True
                        time.sleep(1.2)
                except Exception:
                    pass

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.2)

        post_commenters = set()
        links = driver.find_elements(By.TAG_NAME, "a")

        for link in links:
            try:
                href = link.get_attribute("href")
                if href and "instagram.com/" in href:
                    clean_path = href.split("instagram.com/")[-1].strip("/")
                    parts = [p for p in clean_path.split("/") if p]
                    if parts:
                        uname = parts[0].lower()
                        if (
                            uname not in SYSTEM_EXCLUDED_USERNAMES
                            and uname != my_username
                            and not uname.startswith("?")
                            and not uname.startswith("#")
                            and not uname.isdigit()
                        ):
                            # Retain original username case from link text or URL
                            original_uname = parts[0]
                            post_commenters.add(original_uname)
            except Exception:
                pass

        print(f"[+] Successfully extracted {len(post_commenters)} unique commenters from this post.")
        return post_commenters

    except (NoSuchWindowException, WebDriverException) as e:
        print(f"[!] Browser window was closed or disconnected during crawl.")
        raise e
    except Exception as e:
        print(f"[!] Error processing post {post_url}: {e}")
        return set()


def save_commenters_to_file(output_filename, commenters_list):
    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            for uname in commenters_list:
                f.write(f"{uname}\n")

        with open("followers.txt", "w", encoding="utf-8") as f:
            for uname in commenters_list:
                f.write(f"{uname}\n")
        print(f"[+] Updated 'followers.txt' with {len(commenters_list)} commenters!")
    except Exception as e:
        print(f"[!] Error saving output files: {e}")


def load_post_links_from_file():
    links = []
    if os.path.exists(POST_LINKS_FILE):
        try:
            with open(POST_LINKS_FILE, "r", encoding="utf-8") as f:
                links = [line.strip() for line in f if line.strip() and "instagram.com/" in line]
        except Exception:
            pass
    return links


def main():
    print("=" * 60)
    print("      Instagram Post & Reel Commenter Scraper - 2026   ")
    print("=" * 60)

    post_urls = []

    # Priority 1: Command line arguments
    if len(sys.argv) > 1:
        post_urls = [arg.strip() for arg in sys.argv[1:] if "instagram.com/" in arg]

    # Priority 2: post_links.txt file
    if not post_urls:
        post_urls = load_post_links_from_file()
        if post_urls:
            print(f"[+] Loaded {len(post_urls)} post URL(s) from '{POST_LINKS_FILE}'.")

    # Priority 3: Interactive Prompt / Default Provided URLs
    if not post_urls:
        print("\nEnter Instagram post/reel URLs (separated by spaces or commas).")
        print("Or press ENTER to scrape the 3 default provided reel/post links:")
        user_input = input("Post URLs: ").strip()

        if user_input:
            post_urls = [u.strip() for u in re.split(r'[\s,]+', user_input) if "instagram.com/" in u]
        else:
            post_urls = [
                "https://www.instagram.com/reel/DakwphaAifc/",
                "https://www.instagram.com/p/DV1HfcyDlru/",
                "https://www.instagram.com/p/DP83EtNjVvW/"
            ]

    if not post_urls:
        print("[!] No valid Instagram post URLs provided. Exiting.")
        return

    print(f"\n[+] Processing {len(post_urls)} post/reel URL(s):")
    for idx, u in enumerate(post_urls, 1):
        print(f"  {idx}. {u}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"commenters_{timestamp}.txt"

    driver = None
    all_commenters = set()

    try:
        driver = get_stealth_driver(headless=False)
        if not login_if_needed(driver):
            print("[!] Cannot proceed without logged in session.")
            return

        creds = load_credentials()
        my_username = creds[0].lower() if creds else ""

        for idx, url in enumerate(post_urls, 1):
            print(f"\n[Post #{idx}/{len(post_urls)}] Scraping commenters...")
            try:
                post_users = scrape_commenters_from_post(driver, url, my_username=my_username)
                all_commenters.update(post_users)
                print(f"[+] Total unique commenters collected so far: {len(all_commenters)}")

                # Save progress after every post
                save_commenters_to_file(output_filename, list(all_commenters))
            except NoSuchWindowException:
                print("\n[!] Browser window closed by user. Auto-saving progress...")
                break
            except WebDriverException as e:
                print(f"\n[!] Browser connection error: {e}. Auto-saving progress...")
                break

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    if all_commenters:
        save_commenters_to_file(output_filename, list(all_commenters))
        print(f"\n[SUCCESS] Saved {len(all_commenters)} unique commenters to '{output_filename}' and 'followers.txt'!")
    else:
        print("[!] No commenters retrieved.")


if __name__ == "__main__":
    main()
