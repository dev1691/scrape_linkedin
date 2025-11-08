#!/usr/bin/env python3
"""
app.py

FastAPI server that:
 - reads LINKEDIN_EMAIL and LINKEDIN_PASSWORD from .env / environment
 - provides POST /search to run a LinkedIn search and extract profiles that have resumes attached
 - collects profiles from search results using a primary Selenium driver
 - checks profiles in parallel using ThreadPoolExecutor (each worker creates & logs in its own driver)
 - saves results to CSV in /app/output and logs to /app/logs/app.log (rotating)
"""

import os
import time
import json
import re
import random
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import pandas as pd

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

# Load environment
load_dotenv()
LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")
HEADLESS = os.getenv("HEADLESS", "true").lower() in ("1", "true", "yes")
CHROME_BIN = os.getenv("CHROME_BIN", "/usr/bin/chromium")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "/app/output")
LOG_DIR = os.getenv("LOG_DIR", "/app/logs")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
    raise SystemExit("LINKEDIN_EMAIL and LINKEDIN_PASSWORD must be set in environment or .env")

# Logging setup with RotatingFileHandler
logger = logging.getLogger("linkedin_scraper")
logger.setLevel(logging.INFO)
log_path = os.path.join(LOG_DIR, "app.log")
handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
# Also log to console
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

logger.info("Starting LinkedIn scraper service")

# Constants and regex
SEARCH_XPATH = "/html/body/div[5]/header/div/div/div/div[1]/input"
SEARCH_QUERY_DEFAULT = "Software Engineer"
MAX_PROFILES_DEFAULT = 20
MAX_WORKERS = 6  # number of parallel profile-checking threads
SEARCH_RESULTS_UL_CSS = "ul[role='list']"
RESUME_REGEX = re.compile(r"\.pdf|\.docx|\.doc|resume|cv", re.IGNORECASE)


# Request body model
class SearchRequest(BaseModel):
    query: str
    max_profiles: Optional[int] = MAX_PROFILES_DEFAULT


app = FastAPI(title="LinkedIn Scraper API")


def create_driver(headless: bool = True):
    """Create and configure a Chrome WebDriver instance.

    Prefer using system chromedriver (CHROMEDRIVER_PATH) that matches apt-installed Chromium.
    Fallback to webdriver-manager only if system chromedriver is not available.
    """
    options = webdriver.ChromeOptions()
    # ensure binary path if present
    if os.path.exists(CHROME_BIN):
        options.binary_location = CHROME_BIN

    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1400,1000")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-extensions")
    options.add_argument("user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0 Safari/537.36")

    # Preferred: use system-installed chromedriver if available
    chromedriver_env = os.getenv("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
    if os.path.exists(chromedriver_env):
        service = ChromeService(executable_path=chromedriver_env)
        driver = webdriver.Chrome(service=service, options=options)
        try:
            # anti-detection tweak
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })
        except Exception:
            pass
        return driver

    # Fallback: use webdriver-manager to download a driver that matches installed/chosen browser
    # We limit webdriver-manager's probing to reduce noise. It will still try to detect local browsers.
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            })
        except Exception:
            pass
        return driver
    except Exception as e:
        # give a clear error with guidance
        logger.exception("Failed to start Chrome webdriver: %s", e)
        raise RuntimeError(
            "Could not start chromedriver. Ensure chromedriver matching the Chromium/Chrome version "
            "is installed in the container or set CHROMEDRIVER_PATH env var to the chromedriver binary."
        )

def login_linkedin(driver, timeout=20):
    """Log into LinkedIn using provided driver. Raises RuntimeError if login fails."""
    wait = WebDriverWait(driver, timeout)
    driver.get("https://www.linkedin.com/login")
    try:
        username = wait.until(EC.presence_of_element_located((By.ID, "username")))
        password = wait.until(EC.presence_of_element_located((By.ID, "password")))
    except TimeoutException:
        logger.error("Login page did not load correctly.")
        raise RuntimeError("Login page did not load or LinkedIn changed login selectors")

    username.clear()
    username.send_keys(LINKEDIN_EMAIL)
    password.clear()
    password.send_keys(LINKEDIN_PASSWORD)
    password.send_keys(Keys.RETURN)

    # wait for post-login element (search or profile avatar)
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='Search']")))
    except TimeoutException:
        # fallback to 'Me' avatar
        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "img.global-nav__me-photo, button[aria-label*='Me']")))
        except TimeoutException:
            raise RuntimeError("Login didn't complete — possible 2FA or blocking.")

    # brief sleep for JS
    time.sleep(1.5)
    return True


def search_and_collect_profiles(driver, query: str, max_profiles: int = MAX_PROFILES_DEFAULT, timeout=15) -> List[Dict[str, Any]]:
    """Use driver to perform the search and collect profile URLs (up to max_profiles)."""
    wait = WebDriverWait(driver, timeout)

    # Try to find the requested absolute XPath search input (the explicit XPath you gave)
    try:
        search_input = wait.until(EC.presence_of_element_located((By.XPATH, SEARCH_XPATH)))
    except TimeoutException:
        # fallback to placeholder
        try:
            search_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder='Search']")))
        except TimeoutException:
            logger.error("Search input not found after login.")
            raise RuntimeError("Search input not found")

    search_input.clear()
    search_input.send_keys(query)
    search_input.send_keys(Keys.RETURN)

    # wait for result list
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, SEARCH_RESULTS_UL_CSS)))
    except TimeoutException:
        logger.warning("Search results list did not appear immediately; continuing after brief wait.")
        time.sleep(2)

    profiles = []
    seen = set()
    last_height = driver.execute_script("return document.body.scrollHeight")
    scroll_tries = 0

    while len(profiles) < max_profiles and scroll_tries < 30:
        lis = driver.find_elements(By.CSS_SELECTOR, f"{SEARCH_RESULTS_UL_CSS} > li")
        for li in lis:
            if len(profiles) >= max_profiles:
                break
            try:
                a = li.find_element(By.CSS_SELECTOR, "a.yRgCVsjrzAHkdCEjqvAcmnsmCUhbwIZbY")
                href = a.get_attribute("href")
                if href and href not in seen:
                    profiles.append({"profile_url": href})
                    seen.add(href)
            except Exception:
                try:
                    a2 = li.find_element(By.TAG_NAME, "a")
                    href = a2.get_attribute("href")
                    if href and href not in seen:
                        profiles.append({"profile_url": href})
                        seen.add(href)
                except Exception:
                    continue

        # scroll to load more
        driver.execute_script("window.scrollBy(0, window.innerHeight);")
        time.sleep(1 + random.random() * 0.5)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            scroll_tries += 1
        else:
            last_height = new_height
            scroll_tries = 0

    logger.info("Collected %d profile candidates from search", len(profiles))
    return profiles[:max_profiles]


def detect_resume_worker(profile: Dict[str, Any], headless=True, timeout=12) -> Dict[str, Any]:
    """
    Worker that creates its own driver, logs in, fetches the profile page and heuristically checks for resumes.
    Returns dict with name, profile_url, resume_found, resume_links, error (optional).
    """
    result = {
        "profile_url": profile.get("profile_url"),
        "resume_found": False,
        "resume_links": [],
        "error": None,
    }
    driver = None
    try:
        driver = create_driver(headless=headless)
        login_linkedin(driver, timeout=15)
        # tiny randomized delay
        time.sleep(0.7 + random.random() * 0.8)
        driver.get(profile["profile_url"])
        # let JS load
        time.sleep(1.5 + random.random() * 1.0)
        page_html = driver.page_source
        if RESUME_REGEX.search(page_html):
            # find anchors with file links or containing 'resume'/'cv'
            anchors = driver.find_elements(By.TAG_NAME, "a")
            links = []
            for a in anchors:
                try:
                    href = a.get_attribute("href") or ""
                    if re.search(r"\.pdf|\.docx|\.doc", href, re.IGNORECASE) or re.search(r"resume|cv", href, re.IGNORECASE):
                        links.append(href)
                except Exception:
                    continue
            # dedupe
            links = list(dict.fromkeys(links))
            result["resume_found"] = True
            result["resume_links"] = links
        # small polite delay before quitting
        time.sleep(0.2 + random.random() * 0.4)
    except Exception as e:
        logger.exception("Worker error for profile %s: %s", profile.get("profile_url"), str(e))
        result["error"] = str(e)
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
    return result


@app.post("/search")
def search_endpoint(req: SearchRequest):
    """
    POST /search
    Body: { "query": "Software Engineer", "max_profiles": 20 }
    Returns: JSON with path to CSV and summary.
    This endpoint performs the whole flow synchronously and returns after completion.
    """
    query = req.query.strip()
    max_profiles = req.max_profiles or MAX_PROFILES_DEFAULT
    logger.info("Received search request: query=%s max_profiles=%d", query, max_profiles)

    driver = None
    try:
        driver = create_driver(headless=HEADLESS)
        logger.info("Primary driver created, logging in for search...")
        login_linkedin(driver)
        logger.info("Logged in. Starting search for query: %s", query)
        profiles = search_and_collect_profiles(driver, query, max_profiles=max_profiles)
        if not profiles:
            raise HTTPException(status_code=404, detail="No profiles found for the given query")

        # Use ThreadPoolExecutor to check profiles in parallel
        results = []
        found_count = 0
        logger.info("Starting ThreadPoolExecutor with max_workers=%d", MAX_WORKERS)
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_profile = {executor.submit(detect_resume_worker, p, HEADLESS): p for p in profiles}
            for future in as_completed(future_to_profile):
                res = future.result()
                results.append(res)
                if res.get("resume_found"):
                    found_count += 1
                logger.info("Checked profile: %s resume_found=%s", res.get("profile_url"), res.get("resume_found"))

        # Save results to CSV
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        csv_filename = f"results_{query.replace(' ', '_')}_{timestamp}.csv"
        csv_path = os.path.join(OUTPUT_DIR, csv_filename)
        df = pd.DataFrame(results)
        df.to_csv(csv_path, index=False)
        logger.info("Saved CSV to %s (found %d profiles with resume heuristics)", csv_path, found_count)

        return {
            "status": "completed",
            "query": query,
            "profiles_checked": len(results),
            "resumes_found": found_count,
            "csv_path": csv_path,
            "results_preview": results[:10],  # small preview in response
        }
    except HTTPException as he:
        logger.error("HTTP error: %s", he.detail)
        raise he
    except Exception as e:
        logger.exception("Fatal error while processing search")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
