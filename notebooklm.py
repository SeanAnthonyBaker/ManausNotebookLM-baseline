import os
import time
import logging
import threading
import json
from typing import Optional

from flask import Blueprint, jsonify, request, Response, stream_with_context
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium import webdriver

notebooklm_bp = Blueprint('notebooklm', __name__)
logger = logging.getLogger(__name__)

# --- Global State Management for Selenium ---
# A single, shared browser instance and a lock to ensure thread safety.
browser_instance: Optional[WebDriver] = None
browser_lock = threading.Lock()

# --- Constants for Selenium Selectors ---
CHAT_INPUT_SELECTORS = [
    (By.CSS_SELECTOR, '[data-testid="chat-input"]'),
    (By.XPATH, "//textarea[contains(@placeholder, 'Start typing')]"),
    (By.XPATH, "//input[contains(@placeholder, 'Start typing')]"),
    (By.CSS_SELECTOR, 'textarea[placeholder*="Ask"]'),
    (By.CSS_SELECTOR, '.chat-input textarea'),
    (By.CSS_SELECTOR, 'textarea[aria-label*="Ask"]')
]

SUBMIT_BUTTON_SELECTORS = [
    (By.CSS_SELECTOR, 'button[data-testid="send-button"]'),
    (By.CSS_SELECTOR, 'button[aria-label*="Send"]'),
    (By.XPATH, "//button[@aria-label='Submit' or @type='submit']")
]

RESPONSE_CONTENT_SELECTOR = (By.CSS_SELECTOR, '.message-content')

NOTEBOOKLM_LOAD_INDICATORS = [
    (By.CSS_SELECTOR, '[data-testid="chat-input"]'), # Chat input is a good sign of readiness
    (By.CSS_SELECTOR, 'div[aria-label="Sources"]'), # Sources panel
    (By.XPATH, "//*[contains(text(), 'New notebook')]") # "New notebook" button
]


def initialize_browser():
    """
    Initializes the shared browser instance. This should be called once at application startup.
    """
    global browser_instance
    
    # Use a remote WebDriver to connect to the Selenium container
    selenium_hub_url = os.environ.get('SELENIUM_HUB_URL', 'http://localhost:4444/wd/hub')
    
    logger.info(f"Attempting to connect to Selenium Hub at: {selenium_hub_url}")
    
    chrome_options = Options()
    
    # --- Anti-detection options ---
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    # Using a realistic or slightly future-dated User-Agent helps avoid bot detection.
    # This is configurable via the CHROME_USER_AGENT environment variable.
    default_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/138.0.7204.157 Safari/537.36'
    user_agent = os.environ.get('CHROME_USER_AGENT', default_user_agent)
    chrome_options.add_argument(f'user-agent={user_agent}')

    # This points to the profile directory mounted inside the Selenium container
    chrome_options.add_argument("--user-data-dir=/data")
    chrome_options.add_argument("--profile-directory=Default")

    try:
        browser_instance = webdriver.Remote(
            command_executor=selenium_hub_url,
            options=chrome_options
        )
        browser_instance.set_page_load_timeout(60)
        logger.info("WebDriver initialized successfully and connected to Selenium Hub.")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize WebDriver: {e}", exc_info=True)
        browser_instance = None
        return False

def start_browser_initialization_thread():
    """Starts the browser initialization in a background thread to not block app startup."""
    init_thread = threading.Thread(target=initialize_browser, daemon=True)
    init_thread.start()

def find_element_by_priority(driver, selectors, condition=EC.presence_of_element_located, timeout=10):
    """
    Tries to find an element by iterating through a list of selectors.
    This implementation polls for the element to avoid a multiplicative timeout effect.
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        for by, value in selectors:
            try:
                element = condition((by, value))(driver)
                if element:
                    return element
            except (NoSuchElementException, StaleElementReferenceException):
                pass
        time.sleep(0.2)

    logger.debug(f"Element not found using any selector within the {timeout}s timeout.")
    return None


@notebooklm_bp.route('/process_query', methods=['POST'])
def process_query():
    """
    Consolidated Endpoint: Opens NotebookLM, submits a query, streams the response, and closes the browser.
    """
    data = request.get_json()
    if not data or 'query' not in data:
        return jsonify({'error': 'Missing "query" in request body'}), 400
    
    url = data.get('notebooklm_url', "https://notebooklm.google.com/")
    logger.info(f"DEBUG: process_query received URL: '{url}'")
    query_text = data['query']
    timeout = data.get('timeout', 180)

    def generate_full_process_response():
        global browser_instance
        
        # 1. Initialize and Open
        with browser_lock:
            if not browser_instance:
                if not initialize_browser():
                     yield f'data: {json.dumps({"error": "Failed to initialize browser."})}\n\n'
                     return
            
            try:
                logger.info(f"Navigating to {url}...")
                yield f'data: {json.dumps({"status": "opening_browser", "message": f"Navigating to {url}"})}\n\n'
                
                browser_instance.get(url)
                
                # Wait for initial load
                time.sleep(5) 
                
                current_url = browser_instance.current_url
                logger.info(f"Current URL after navigation: {current_url}")
                
                if 'accounts.google.com' in current_url or 'signin' in current_url.lower():
                    logger.warning(f"Redirected to Google sign-in page.")
                    yield f'data: {json.dumps({"status": "authentication_required", "message": "Redirected to Google sign-in. Waiting 5 minutes for manual login..."})}\n\n'
                    
                    # Wait up to 5 minutes for user to log in
                    auth_timeout = 300
                    auth_start_time = time.time()
                    logged_in = False
                    
                    while time.time() - auth_start_time < auth_timeout:
                        if "notebooklm.google.com" in browser_instance.current_url and find_element_by_priority(browser_instance, CHAT_INPUT_SELECTORS, timeout=1):
                            logged_in = True
                            break
                        time.sleep(2)
                    
                    if not logged_in:
                        logger.error("Timed out waiting for manual login.")
                        yield f'data: {json.dumps({"error": "Timed out waiting for manual login."})}\n\n'
                        return
                    else:
                        logger.info("User logged in successfully.")
                        yield f'data: {json.dumps({"status": "login_success", "message": "Login detected. Proceeding..."})}\n\n'

                # Wait for page to fully load
                logger.info("Waiting for page to fully load...")
                time.sleep(5)
                
                # Ensure we are on the correct page with retry logic
                max_retries = 3
                target_id = url.split('/')[-1] if 'notebook/' in url else ''
                
                for i in range(max_retries):
                    current_url = browser_instance.current_url
                    
                    # 1. Check if we are on the home page but want a specific notebook
                    if "notebook/" in url and "notebook/" not in current_url:
                        logger.warning(f"Attempt {i+1}/{max_retries}: Detected Home Page (or non-notebook page) '{current_url}' but target is '{url}'. Re-navigating...")
                        browser_instance.get(url)
                        time.sleep(8) # Increased wait time
                        continue

                    # 2. Check if we are on the WRONG notebook (ID mismatch)
                    if target_id and target_id not in current_url:
                        logger.warning(f"Attempt {i+1}/{max_retries}: ID mismatch. Current '{current_url}' vs Target '{url}'. Re-navigating...")
                        browser_instance.get(url)
                        time.sleep(8)
                        continue

                    # 3. Success check
                    logger.info(f"Successfully on target page: {current_url}")
                    break
                else:
                    logger.error(f"Failed to navigate to {url} after {max_retries} attempts. Current URL: {browser_instance.current_url}")

                logger.info(f"Page loaded. Current URL: {browser_instance.current_url}")
                yield f'data: {json.dumps({"status": "browser_ready", "message": "NotebookLM interface loaded."})}\n\n'

                # 2. Query Logic
                if "notebooklm.google.com" not in browser_instance.current_url:
                     yield f'data: {json.dumps({"error": "Not on a NotebookLM page."})}\n\n'
                     return
                
                initial_response_count = len(browser_instance.find_elements(*RESPONSE_CONTENT_SELECTOR))
                
                logger.info("Attempting to find the chat input field...")
                input_field = find_element_by_priority(browser_instance, CHAT_INPUT_SELECTORS, condition=EC.element_to_be_clickable, timeout=10)
                if not input_field:
                    raise NoSuchElementException("Could not find the chat input field.")
                
                logger.info(f"Entering query text: {query_text}")
                input_field.clear()
                input_field.send_keys(query_text)
                
                submit_button = find_element_by_priority(browser_instance, SUBMIT_BUTTON_SELECTORS, condition=EC.element_to_be_clickable, timeout=5)
                if submit_button:
                    logger.info("Clicking submit button...")
                    submit_button.click()
                else:
                    logger.info("Submit button not found, sending RETURN key...")
                    from selenium.webdriver.common.keys import Keys
                    input_field.send_keys(Keys.RETURN)
                
                logger.info("Query submitted.")
                yield f'data: {json.dumps({"status": "waiting_for_response"})}\n\n'

                def find_new_response_with_text(driver, initial_count, selector):
                    try:
                        response_elements = driver.find_elements(*selector)
                        if len(response_elements) > initial_count:
                            new_response_element = response_elements[-1]
                            if new_response_element.is_displayed() and new_response_element.text.strip():
                                return new_response_element
                    except StaleElementReferenceException:
                        return False
                    return False

                try:
                    response_element = WebDriverWait(browser_instance, 50).until(
                        lambda d: find_new_response_with_text(d, initial_response_count, RESPONSE_CONTENT_SELECTOR)
                    )
                    logger.info("Response started.")
                    yield f'data: {json.dumps({"status": "streaming"})}\n\n'
                except TimeoutException:
                    logger.error("Timeout waiting for response generation.")
                    yield f'data: {json.dumps({"error": "NotebookLM did not start generating response."})}\n\n'
                    return

                last_text = ""
                end_time = time.time() + timeout
                stream_completed = False
                last_data_time = time.time()
                INACTIVITY_TIMEOUT = 10

                while time.time() < end_time:
                    try:
                        current_text = response_element.text
                    except StaleElementReferenceException:
                        response_element = browser_instance.find_elements(*RESPONSE_CONTENT_SELECTOR)[-1]
                        current_text = response_element.text
                        last_text = ""

                    if len(current_text) > len(last_text):
                        new_text = current_text[len(last_text):]
                        yield f'data: {json.dumps({"chunk": new_text})}\n\n'
                        last_text = current_text
                        last_data_time = time.time()

                    if time.time() - last_data_time > INACTIVITY_TIMEOUT:
                        stream_completed = True
                        break
                    
                    time.sleep(0.2)
                
                final_text = response_element.text
                if len(final_text) > len(last_text):
                    new_text = final_text[len(last_text):]
                    yield f'data: {json.dumps({"chunk": new_text})}\n\n'

                status_message = "timeout" if not stream_completed else "complete"
                yield f'data: {json.dumps({"status": status_message})}\n\n'

            except Exception as e:
                logger.error(f"Error in process_query: {e}", exc_info=True)
                yield f'data: {json.dumps({"error": str(e)})}\n\n'
            
            finally:
                # 3. Close Browser
                if browser_instance:
                    try:
                        browser_instance.quit()
                        logger.info("Browser closed.")
                        browser_instance = None
                        yield f'data: {json.dumps({"status": "browser_closed"})}\n\n'
                    except Exception as e:
                        logger.error(f"Error closing browser: {e}")

    return Response(stream_with_context(generate_full_process_response()), mimetype='text/event-stream')

@notebooklm_bp.route('/open_notebooklm', methods=['POST'])
def open_notebooklm():
    """
    Endpoint 1: Navigates to a specific NotebookLM URL. This endpoint is ASYNCHRONOUS.
    It will start loading the page in the background and return immediately.
    """
    data = request.get_json() or {}
    url = data.get('notebooklm_url', "https://notebooklm.google.com/")
    logger.info(f"Request received to open URL: {url}")

    # Start the page load in a background thread
    thread = threading.Thread(target=_perform_open_notebook, args=(url,))
    thread.daemon = True
    thread.start()

    return jsonify({'status': 'loading', 'message': f'Page load initiated for {url}'}), 202

def _perform_open_notebook(url):
    """
    Helper function to contain the browser navigation and validation logic.
    This runs in a background thread and does not return a direct response to the client.
    """
    with browser_lock:
        if not browser_instance:
            logger.error("Browser not initialized.")
            return
        try:
            logger.info(f"Navigating to {url} and waiting for it to become interactive...")
            browser_instance.get(url)

            load_indicator = find_element_by_priority(browser_instance, NOTEBOOKLM_LOAD_INDICATORS, timeout=20)

            current_url = browser_instance.current_url
            if 'accounts.google.com' in current_url or 'signin' in current_url.lower():
                logger.warning(f"Redirected to Google sign-in page for URL: {url}")
            elif not load_indicator:
                logger.error(f"Timed out waiting for NotebookLM interface to load at {url}.")
            else:
                logger.info(f"Successfully navigated to {url} and the interface is ready.")
        except Exception as e:
            logger.error(f"Error during open of {url}: {e}", exc_info=True)

@notebooklm_bp.route('/query_notebooklm', methods=['POST'])
def query_notebooklm():
    """
    Endpoint 2: Submits a query to NotebookLM and streams the response back.
    """
    data = request.get_json()
    if not data or 'query' not in data:
        return jsonify({'error': 'Missing "query" in request body'}), 400
    query_text = data['query']
    timeout = data.get('timeout', 180) # Allow configurable timeout

    def generate_response():
        with browser_lock:
            if not browser_instance:
                yield f'data: {json.dumps({"error": "Browser not initialized."})}\n\n'
                return

            try:
                # Check if we are on a valid NotebookLM page
                if "notebooklm.google.com" not in browser_instance.current_url:
                    yield f'data: {json.dumps({"error": "Not on a NotebookLM page. Please use /open_notebooklm first."})}\n\n'
                    return

                initial_response_count = len(browser_instance.find_elements(*RESPONSE_CONTENT_SELECTOR))
                
                logger.info("Attempting to find the chat input field...")
                input_field = find_element_by_priority(browser_instance, CHAT_INPUT_SELECTORS, condition=EC.element_to_be_clickable, timeout=10)
                if not input_field:
                    raise NoSuchElementException("Could not find the chat input field.")
                
                input_field.clear()
                input_field.send_keys(query_text)
                
                submit_button = find_element_by_priority(browser_instance, SUBMIT_BUTTON_SELECTORS, condition=EC.element_to_be_clickable, timeout=5)
                if submit_button:
                    submit_button.click()
                else:
                    from selenium.webdriver.common.keys import Keys
                    input_field.send_keys(Keys.RETURN)
                
                logger.info("Query submitted, waiting for response from NotebookLM...")
                yield f'data: {json.dumps({"status": "waiting_for_response"})}\n\n'

                def find_new_response_with_text(driver, initial_count, selector):
                    try:
                        response_elements = driver.find_elements(*selector)
                        if len(response_elements) > initial_count:
                            new_response_element = response_elements[-1]
                            if new_response_element.is_displayed() and new_response_element.text.strip():
                                return new_response_element
                    except StaleElementReferenceException:
                        return False
                    return False

                try:
                    response_element = WebDriverWait(browser_instance, 50).until(
                        lambda d: find_new_response_with_text(d, initial_response_count, RESPONSE_CONTENT_SELECTOR)
                    )
                    logger.info("First text chunk detected. Starting to stream content.")
                    yield f'data: {json.dumps({"status": "streaming"})}\n\n'
                except TimeoutException:
                    logger.error("Timed out waiting for a response from NotebookLM to start generating.")
                    yield f'data: {json.dumps({"error": "NotebookLM did not start generating a response in time."})}\n\n'
                    return

                last_text = ""
                end_time = time.time() + timeout
                stream_completed = False
                last_data_time = time.time()
                INACTIVITY_TIMEOUT = 10

                while time.time() < end_time:
                    try:
                        current_text = response_element.text
                    except StaleElementReferenceException:
                        logger.warning("Response element became stale. Re-finding...")
                        response_element = browser_instance.find_elements(*RESPONSE_CONTENT_SELECTOR)[-1]
                        current_text = response_element.text
                        last_text = ""

                    if len(current_text) > len(last_text):
                        new_text = current_text[len(last_text):]
                        yield f'data: {json.dumps({"chunk": new_text})}\n\n'
                        last_text = current_text
                        last_data_time = time.time()

                    if time.time() - last_data_time > INACTIVITY_TIMEOUT:
                        logger.info(f"Stream complete: No new data for {INACTIVITY_TIMEOUT} seconds.")
                        stream_completed = True
                        break
                    
                    time.sleep(0.2)

                final_text = response_element.text
                if len(final_text) > len(last_text):
                    new_text = final_text[len(last_text):]
                    yield f'data: {json.dumps({"chunk": new_text})}\n\n'

                status_message = "timeout" if not stream_completed else "complete"
                yield f'data: {json.dumps({"status": status_message})}\n\n'

            except Exception as e:
                logger.error(f"An unexpected error occurred during the query stream: {e}", exc_info=True)
                yield f'data: {json.dumps({"error": str(e)})}\n\n'

    return Response(stream_with_context(generate_response()), mimetype='text/event-stream')

@notebooklm_bp.route('/status', methods=['GET'])
def get_status():
    """Endpoint 4: Checks the status of the browser instance."""
    with browser_lock:
        if browser_instance:
            try:
                current_url = browser_instance.current_url
                page_title = browser_instance.title
                status = 'ready'
                if 'accounts.google.com' in current_url or 'signin' in current_url.lower():
                    status = 'authentication_required'
                
                return jsonify({
                    'browser_active': True,
                    'status': status,
                    'current_url': current_url,
                    'page_title': page_title
                })
            except Exception as e:
                logger.error(f"Error getting browser status: {e}")
                return jsonify({'browser_active': False, 'status': 'error', 'error': str(e)}), 500
        else:
            return jsonify({'browser_active': False, 'status': 'inactive'})

@notebooklm_bp.route('/close_browser', methods=['POST'])
def close_browser():
    """Endpoint 3: Closes the browser instance."""
    global browser_instance
    with browser_lock:
        if browser_instance:
            try:
                browser_instance.quit()
                logger.info("Browser instance closed by API call.")
            except Exception as e:
                logger.error(f"Error closing browser: {e}")
            finally:
                browser_instance = None
            return jsonify({'success': True, 'message': 'Browser closed successfully.'})
        else:
            return jsonify({'success': False, 'message': 'Browser was not active.'})
