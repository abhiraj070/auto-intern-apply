"""
Automated Internship Application Engine
Supports: Greenhouse, Lever, Ashby, and Generic ATS Forms.
Reads candidate details from profile.json and uploads resume.pdf.
"""

import os
import sys
import json
import time
import argparse
import re
from urllib.parse import urlsplit
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    ElementNotInteractableException,
    WebDriverException
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_FILE = os.path.join(SCRIPT_DIR, "profile.json")


def load_profile():
    if not os.path.exists(PROFILE_FILE):
        print(f"[!] Error: {PROFILE_FILE} not found. Please create it or copy profile.example.json.")
        sys.exit(1)
    with open(PROFILE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_driver(browser_choice="chrome", headless=False):
    """Initializes Chrome or Edge WebDriver."""
    browser_choice = browser_choice.lower()
    driver = None

    # Try Chrome first
    if browser_choice in ["chrome", "auto"]:
        try:
            from selenium.webdriver.chrome.options import Options as ChromeOptions
            from selenium.webdriver.chrome.service import Service as ChromeService
            options = ChromeOptions()
            if headless:
                options.add_argument("--headless=new")
            options.add_argument("--start-maximized")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            driver = webdriver.Chrome(options=options)
            return driver
        except Exception as e:
            if browser_choice == "chrome":
                print(f"[!] Chrome failed: {e}. Falling back to Edge...")

    # Fallback to Edge
    try:
        from selenium.webdriver.edge.options import Options as EdgeOptions
        from selenium.webdriver.edge.service import Service as EdgeService
        options = EdgeOptions()
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-blink-features=AutomationControlled")
        driver = webdriver.Edge(options=options)
        return driver
    except Exception as e:
        print(f"[!] Failed to initialize browser: {e}")
        sys.exit(1)


def fill_input(driver, selector_tuple, value, clear=True):
    """Safely fills an input field if found."""
    if not value:
        return False
    try:
        el = driver.find_element(*selector_tuple)
        if el.is_displayed() and el.is_enabled():
            if clear:
                el.clear()
            el.send_keys(value)
            return True
    except (NoSuchElementException, ElementNotInteractableException):
        pass
    return False


def upload_file(driver, file_path):
    """Uploads resume to file inputs."""
    if not file_path or not os.path.exists(file_path):
        print(f"[!] Resume file not found at: {file_path}")
        return False

    abs_path = os.path.abspath(file_path)
    try:
        file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
        for f_input in file_inputs:
            try:
                f_input.send_keys(abs_path)
                print(f"[OK] Resume uploaded successfully: {os.path.basename(abs_path)}")
                return True
            except Exception:
                continue
    except Exception as e:
        print(f"[!] Error finding file input: {e}")
    return False


def submit_application(driver, selector):
    """Return True only after a visible receipt confirms submission."""
    try:
        if not driver.execute_script("return Array.from(document.forms).every(form => form.checkValidity());"):
            print("[!] Required answers are missing or invalid; review the form.")
            return False
        receipt = re.compile(
            r"(?:your\s+)?application\s+(?:has been\s+|was\s+)?(?:successfully\s+)?(?:submitted|received)"
            r"|thank you for applying|thanks for applying", re.IGNORECASE)
        def confirmed(browser):
            return bool(receipt.search(browser.find_element(By.TAG_NAME, "body").text))

        # A pre-existing receipt must not be mistaken for a new submission.
        if confirmed(driver):
            print("[!] A receipt is already visible; no new submission attempted.")
            return False
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable(selector)).click()
        WebDriverWait(driver, 20).until(confirmed)
        print("[OK] Application submission confirmed.")
        return True
    except (WebDriverException, TimeoutException) as e:
        print(f"[!] Submission not confirmed: {e}. Review before retrying.")
        return False


# ==============================================================================
# Lever Application Handler
# ==============================================================================
def apply_lever(driver, profile, resume_path, auto_submit=False):
    print("[*] Detected Lever application form.")
    p_info = profile.get("personal_info", {})
    links = profile.get("online_presence", {})
    edu = profile.get("education", {})

    time.sleep(2)  # Wait for page elements to settle

    # Name
    name_ok = fill_input(driver, (By.NAME, "name"), p_info.get("full_name", ""))
    
    # Email
    email_ok = fill_input(driver, (By.NAME, "email"), p_info.get("email", ""))
    
    # Phone
    fill_input(driver, (By.NAME, "phone"), p_info.get("phone", ""))
    
    # Current Company / Organization / University
    fill_input(driver, (By.NAME, "org"), edu.get("school", ""))
    
    # URLs
    fill_input(driver, (By.NAME, "urls[LinkedIn]"), links.get("linkedin", ""))
    fill_input(driver, (By.NAME, "urls[GitHub]"), links.get("github", ""))
    fill_input(driver, (By.NAME, "urls[Portfolio]"), links.get("portfolio", ""))
    fill_input(driver, (By.NAME, "urls[Other]"), links.get("portfolio", ""))

    # Resume
    resume_ok = upload_file(driver, resume_path)
    # Custom radio questions require their own context. Leave them for review;
    # the India-specific authorization profile cannot answer foreign eligibility.
    print("[*] Review custom questions, including work authorization, manually.")

    print("[OK] Lever form auto-filled!")
    if auto_submit:
        if not (name_ok and email_ok and resume_ok):
            print("[!] Contact details or resume were not filled; automatic submission stopped.")
            return False
        return submit_application(driver, (By.CSS_SELECTOR, "button[type='submit'], #btn-submit"))
    return False


# ==============================================================================
# Greenhouse Application Handler
# ==============================================================================
def apply_greenhouse(driver, profile, resume_path, auto_submit=False):
    print("[*] Detected Greenhouse application form.")
    p_info = profile.get("personal_info", {})
    links = profile.get("online_presence", {})
    edu = profile.get("education", {})

    time.sleep(2)

    # First & Last Name
    first_ok = fill_input(driver, (By.ID, "first_name"), p_info.get("first_name", ""))
    last_ok = fill_input(driver, (By.ID, "last_name"), p_info.get("last_name", ""))
    
    # Fallback to combined name
    combined_ok = fill_input(driver, (By.NAME, "job_application[name]"), p_info.get("full_name", ""))

    # Email & Phone
    email_ok = fill_input(driver, (By.ID, "email"), p_info.get("email", ""))
    fill_input(driver, (By.ID, "phone"), p_info.get("phone", ""))

    # Location
    fill_input(driver, (By.ID, "job_application_location"), f"{p_info.get('location', {}).get('city', '')}, India")

    # Resume Upload
    resume_ok = upload_file(driver, resume_path)

    # LinkedIn / Website / GitHub custom questions
    try:
        all_text_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='url']")
        for inp in all_text_inputs:
            name_attr = (inp.get_attribute("name") or "").lower()
            id_attr = (inp.get_attribute("id") or "").lower()
            aria_label = (inp.get_attribute("aria-label") or "").lower()

            combined = f"{name_attr} {id_attr} {aria_label}"
            if "linkedin" in combined:
                fill_input(driver, (By.ID, inp.get_attribute("id")), links.get("linkedin", ""))
            elif "github" in combined:
                fill_input(driver, (By.ID, inp.get_attribute("id")), links.get("github", ""))
            elif "portfolio" in combined or "website" in combined:
                fill_input(driver, (By.ID, inp.get_attribute("id")), links.get("portfolio", ""))
    except Exception:
        pass

    print("[OK] Greenhouse form auto-filled!")
    if auto_submit:
        if not ((first_ok and last_ok or combined_ok) and email_ok and resume_ok):
            print("[!] Contact details or resume were not filled; automatic submission stopped.")
            return False
        return submit_application(driver, (By.ID, "submit_app"))
    return False


# ==============================================================================
# Ashby Application Handler
# ==============================================================================
def apply_ashby(driver, profile, resume_path, auto_submit=False):
    print("[*] Detected Ashby application form.")
    p_info = profile.get("personal_info", {})
    links = profile.get("online_presence", {})

    time.sleep(2)

    # Name, Email, Phone
    fill_input(driver, (By.NAME, "name"), p_info.get("full_name", ""))
    fill_input(driver, (By.NAME, "email"), p_info.get("email", ""))
    fill_input(driver, (By.NAME, "phoneNumber"), p_info.get("phone", ""))

    # Resume
    upload_file(driver, resume_path)

    # Links
    try:
        linkedin_input = driver.find_element(By.XPATH, "//input[contains(@placeholder, 'LinkedIn') or contains(@name, 'linkedIn')]")
        linkedin_input.send_keys(links.get("linkedin", ""))
    except Exception:
        pass

    try:
        github_input = driver.find_element(By.XPATH, "//input[contains(@placeholder, 'GitHub') or contains(@name, 'github')]")
        github_input.send_keys(links.get("github", ""))
    except Exception:
        pass

    print("[OK] Ashby form auto-filled!")
    if auto_submit:
        print("[!] Ashby automatic submission is unsupported; manual review is required.")
    return False


# ==============================================================================
# Generic Form Fallback
# ==============================================================================
def apply_generic(driver, profile, resume_path, auto_submit=False):
    print("[*] Using Generic ATS form matching...")
    p_info = profile.get("personal_info", {})
    links = profile.get("online_presence", {})

    time.sleep(2)

    # Attempt to fill any visible input matching patterns
    inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='email'], input[type='tel'], input[type='url']")
    for inp in inputs:
        identifier = f"{inp.get_attribute('name') or ''} {inp.get_attribute('id') or ''} {inp.get_attribute('placeholder') or ''}".lower()
        if not inp.is_displayed() or not inp.is_enabled():
            continue

        if "first" in identifier and "name" in identifier:
            inp.send_keys(p_info.get("first_name", ""))
        elif "last" in identifier and "name" in identifier:
            inp.send_keys(p_info.get("last_name", ""))
        elif "name" in identifier:
            inp.send_keys(p_info.get("full_name", ""))
        elif "email" in identifier:
            inp.send_keys(p_info.get("email", ""))
        elif "phone" in identifier or "mobile" in identifier or "tel" in identifier:
            inp.send_keys(p_info.get("phone", ""))
        elif "linkedin" in identifier:
            inp.send_keys(links.get("linkedin", ""))
        elif "github" in identifier:
            inp.send_keys(links.get("github", ""))
        elif "portfolio" in identifier or "website" in identifier:
            inp.send_keys(links.get("portfolio", ""))

    upload_file(driver, resume_path)
    print("[OK] Generic form auto-filled!")
    if auto_submit:
        print("[!] Generic automatic submission is unsupported; manual review is required.")
    return False


# ==============================================================================
# Main Runner
# ==============================================================================
def apply_to_job(job_url, mode="assist", browser="chrome"):
    if mode not in {"assist", "auto", "headless"}:
        raise ValueError("Unknown application mode")
    profile = load_profile()
    resume_rel = profile.get("documents", {}).get("resume_path", "./resume.pdf")
    resume_abs = os.path.abspath(os.path.join(SCRIPT_DIR, resume_rel))

    if not os.path.exists(resume_abs):
        print(f"[!] Warning: Resume not found at {resume_abs}")
        print("    Please place your resume PDF in the directory as 'resume.pdf'")

    is_headless = (mode == "headless")
    auto_submit = (mode in ["auto", "headless"])

    print(f"\n[*] Launching browser for: {job_url}")
    print(f"[*] Mode: {mode.upper()} (Assisted review by default)")

    driver = get_driver(browser_choice=browser, headless=is_headless)
    try:
        driver.get(job_url)
        time.sleep(3)

        current_url = driver.current_url.lower()
        host = (urlsplit(current_url).hostname or "").lower()

        # If it's a Lever job page (not apply page yet), click Apply
        if host == "jobs.lever.co" and not urlsplit(current_url).path.rstrip("/").endswith("/apply"):
            try:
                apply_link = driver.find_element(By.XPATH, "//a[contains(translate(text(), 'APPLY', 'apply'), 'apply')]")
                apply_link.click()
                time.sleep(2)
                current_url = driver.current_url.lower()
                host = (urlsplit(current_url).hostname or "").lower()
            except Exception:
                pass

        def belongs_to(domain):
            return host == domain or host.endswith("." + domain)

        if belongs_to("lever.co"):
            handler = apply_lever
        elif belongs_to("greenhouse.io"):
            handler = apply_greenhouse
        elif belongs_to("ashbyhq.com"):
            handler = apply_ashby
        else:
            handler = apply_generic
        supports_auto = handler in (apply_lever, apply_greenhouse)
        if auto_submit and not supports_auto:
            if is_headless:
                print("[!] This ATS does not support headless submission. Use --mode assist.")
                return False
            print("[*] Automatic submission unsupported for this ATS; switching to assisted review.")
        submitted = handler(driver, profile, resume_abs, auto_submit=auto_submit and supports_auto)

        if not submitted and not is_headless:
            print("\n" + "=" * 60)
            print("[ASSISTED REVIEW]: Check the form and any missing answers.")
            print("   Please review the details in your browser window and click Submit.")
            print("=" * 60)
            input("\n👉 Press [Enter] here once you have submitted or closed the browser...")
        return bool(submitted) if auto_submit else True

    except Exception as e:
        print(f"[!] Exception during application: {e}")
        return False
    finally:
        driver.quit()
        print("[✓] Browser closed.")


def main():
    parser = argparse.ArgumentParser(description="Auto Apply Engine for Tech Internships")
    parser.add_argument("url", nargs="?", help="Direct job application URL (Lever, Greenhouse, Ashby, etc.)")
    parser.add_argument("--mode", choices=["assist", "auto", "headless"], default="assist", help="Execution mode")
    parser.add_argument("--browser", choices=["chrome", "edge"], default="chrome", help="Browser to use")
    
    args = parser.parse_args()

    if not args.url:
        print("\n=== Tech Internship Auto-Apply Assistant ===")
        url_input = input("Enter Job Application URL: ").strip()
        if not url_input:
            print("[!] No URL provided. Exiting.")
            sys.exit(0)
        return apply_to_job(url_input, mode=args.mode, browser=args.browser)
    else:
        return apply_to_job(args.url, mode=args.mode, browser=args.browser)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
