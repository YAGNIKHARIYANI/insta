import os
import time
import pickle
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
FOLLOWERS_FILE = "followers.txt"
PROFILE_DIR = os.path.abspath("chrome_profile")


def save_credentials(username, password):
    with open(CREDENTIALS_FILE, "w", encoding="utf-8") as file:
        file.write(f"{username}\n{password}")
    print(f"[+] Saved credentials to {CREDENTIALS_FILE}")


def load_credentials():
    if not os.path.exists(CREDENTIALS_FILE):
        return None

    with open(CREDENTIALS_FILE, "r", encoding="utf-8") as file:
        lines = [line.strip() for line in file if line.strip()]
        if len(lines) >= 2:
            return lines[0], lines[1]

    return None


def prompt_credentials():
    username = input("Enter your Instagram username: ")
    password = input("Enter your Instagram password: ")
    save_credentials(username, password)
    return username, password


def read_usernames_from_file(file_path):
    if not os.path.exists(file_path):
        print(f"[!] {file_path} not found. Creating a default {file_path}...")
        with open(file_path, "w", encoding="utf-8") as file:
            file.write("# Add instagram usernames here, one per line\n")
        return []

    with open(file_path, "r", encoding="utf-8") as file:
        usernames = [line.strip() for line in file if line.strip() and not line.startswith("#")]
    return usernames


def remove_username_from_file(username, file_path):
    if not os.path.exists(file_path):
        return
    with open(file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()

    with open(file_path, "w", encoding="utf-8") as file:
        for line in lines:
            if line.strip() != username:
                file.write(line)


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
            print(f"[!] Error loading cookies from file: {e}")
    return False


def save_session_cookies(driver):
    try:
        cookies = driver.get_cookies()
        with open(COOKIES_FILE, "wb") as f:
            pickle.dump(cookies, f)
        print(f"[+] Saved session cookies to {COOKIES_FILE}")
    except Exception as e:
        print(f"[!] Failed to save cookies: {e}")


def is_logged_in(driver):
    try:
        curr_url = driver.current_url.lower()
        if "login" not in curr_url and "auth_platform" not in curr_url:
            nav = driver.find_elements(By.CSS_SELECTOR, "svg[aria-label='Home'], svg[aria-label='Search'], nav")
            if nav:
                return True
    except Exception:
        pass
    return False


def login_to_instagram(driver, username, password):
    print(f"[+] Navigating to Instagram login for @{username}...")
    driver.get("https://www.instagram.com/accounts/login/")
    time.sleep(4)

    curr_url = driver.current_url.lower()
    if "login" not in curr_url and "auth_platform" not in curr_url:
        print(f"[+] Already logged in as @{username}!")
        save_session_cookies(driver)
        return True

    print(f"[+] Entering credentials from credentials.txt (@{username})...")
    try:
        user_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name='email'], input[name='username'], input[type='text']")
        pass_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name='pass'], input[name='password'], input[type='password']")

        if user_inputs and pass_inputs:
            u_in = user_inputs[0]
            p_in = pass_inputs[0]

            u_in.clear()
            for char in username:
                u_in.send_keys(char)
                time.sleep(0.02)

            time.sleep(0.5)

            p_in.clear()
            for char in password:
                p_in.send_keys(char)
                time.sleep(0.02)

            print("\n" + "=" * 60)
            print(f"[+] Credentials filled for @{username}!")
            print("[+] Waiting 60 seconds for manual login (NO refresh, NO auto-tap)...")
            print("=" * 60)

            # Wait 60 seconds checking URL without refreshing page
            for i in range(20):
                time.sleep(3)
                curr_url = driver.current_url.lower()
                if "login" not in curr_url and "auth_platform" not in curr_url:
                    print(f"[+] Login detected as complete for @{username}!")
                    save_session_cookies(driver)
                    return True
                print(f"[+] Waiting for manual login tap... ({(i + 1) * 3}s / 60s)")
    except Exception as e:
        print(f"[!] Login form error: {e}")

    curr_url = driver.current_url.lower()
    if "login" not in curr_url and "auth_platform" not in curr_url:
        print(f"[+] Login successful for @{username}!")
        save_session_cookies(driver)
        return True
    else:
        print(f"[!] Login timeframe finished. Current URL: {driver.current_url}")
        return False


def like_stories(username, password, usernames):
    driver = get_stealth_driver(headless=False)

    try:
        cookie_loaded = load_saved_cookies(driver)
        if not cookie_loaded or not is_logged_in(driver):
            success = login_to_instagram(driver, username, password)
            if not success:
                print("[!] Unable to log in. Please verify credentials in credentials.txt.")
                return

        print(f"\n[+] Starting story liker for {len(usernames)} user(s)...")

        for follower in list(usernames):
            print(f"\n--- Checking story for: {follower} ---")
            story_url = f"https://www.instagram.com/stories/{follower}/"
            driver.get(story_url)
            time.sleep(4)

            view_story_btns = driver.find_elements(By.XPATH, "//div[contains(text(),'View story')] | //div[contains(text(),'View Story')] | //button[contains(., 'View')]")
            if view_story_btns:
                print(f"[+] Found 'View Story' button for {follower}. Clicking...")
                try:
                    view_story_btns[0].click()
                    time.sleep(3)
                except Exception:
                    pass

            unlikes = driver.find_elements(By.CSS_SELECTOR, "svg[aria-label='Unlike']")
            if unlikes:
                print(f"[INFO] Story of {follower} is already liked!")
                remove_username_from_file(follower, FOLLOWERS_FILE)
                continue

            like_button = None
            strategies = [
                (By.XPATH, "//svg[@aria-label='Like']/ancestor::*[@role='button' or self::button or self::div][1]"),
                (By.CSS_SELECTOR, "svg[aria-label='Like']"),
                (By.XPATH, "//div[@role='button'][.//svg[@aria-label='Like']]"),
                (By.XPATH, "//span//svg[@aria-label='Like']"),
                (By.XPATH, "//div/div/div[2]/div/div/div[1]/div[1]/section/div[1]/div/div/div[1]/div[2]/div[2]/div[1]/div[2]/span/div"),
                (By.XPATH, "//div/div/div[2]/div/div/div[1]/div[1]/section/div[1]/div/div/div[1]/div[2]/div[3]/div[1]/div[2]/span/div"),
            ]

            for by, selector in strategies:
                try:
                    elements = driver.find_elements(by, selector)
                    if elements:
                        like_button = elements[0]
                        break
                except Exception:
                    pass

            if like_button:
                try:
                    like_button.click()
                    print(f"[TRUE] Liked story for user: {follower}")
                    time.sleep(2)
                except Exception:
                    try:
                        driver.execute_script("arguments[0].click();", like_button)
                        print(f"[TRUE] Liked story for user (via JS): {follower}")
                        time.sleep(2)
                    except Exception as e:
                        print(f"[!] Failed to click like button for {follower}: {e}")
            else:
                page_text = driver.page_source.lower()
                if "story unavailable" in page_text or "this story is unavailable" in page_text or "not found" in page_text:
                    print(f"[FALSE] User -> {follower} has no active story or story is unavailable.")
                else:
                    print(f"[?] Like button not found for {follower} (story may have finished or requires interaction).")

            remove_username_from_file(follower, FOLLOWERS_FILE)

    finally:
        driver.quit()


if __name__ == "__main__":
    print("=" * 60)
    print("           Instagram Story Liker - Enhanced 2026           ")
    print("=" * 60)

    credentials = load_credentials()
    if credentials is None:
        username, password = prompt_credentials()
    else:
        username, password = credentials

    print(f"[+] Loaded Username from credentials.txt: {username}")

    usernames = read_usernames_from_file(FOLLOWERS_FILE)
    if not usernames:
        print(f"[!] '{FOLLOWERS_FILE}' is empty or contains no valid usernames.")
        print(f"[!] Please add Instagram usernames to '{FOLLOWERS_FILE}' and run again.")
    else:
        like_stories(username, password, usernames)
