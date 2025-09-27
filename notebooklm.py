import os
import time
import logging
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
from selenium.webdriver.common.keys import Keys

notebooklm_bp = Blueprint('notebooklm', __name__)
logger = logging.getLogger(__name__)

# --- Constants for Selenium Selectors ---
CHAT_INPUT_SELECTORS = [
    (By.XPATH, "//*[@placeholder='Start typing...']")
]

SUBMIT_BUTTON_SELECTORS = [
    (By.CSS_SELECTOR, 'button[data-testid="send-button"]'),
    (By.CSS_SELECTOR, 'button[aria-label*="Send"]'),
    (By.XPATH, "//button[@aria-label='Submit' or @type='submit']")
]

RESPONSE_CONTENT_SELECTOR = (By.CSS_SELECTOR, '.message-content')

NOTEBOOKLM_LOAD_INDICATORS = [
    (By.TAG_NAME, 'body'), # A very basic check that the page has a body
    (By.CSS_SELECTOR, '[data-testid="chat-input"]'), # Chat input is a good sign of readiness
    (By.CSS_SELECTOR, 'div[aria-label="Sources"]'), # Sources panel
    (By.XPATH, "//*[contains(text(), 'New notebook')]") # "New notebook" button
]

def initialize_browser_for_query():
    """
    Initializes a new browser instance for a single query.
    """
    selenium_hub_url = os.environ.get('SELENIUM_HUB_URL', 'http://localhost:4444/wd/hub')
    logger.info(f"Connecting to Selenium Hub for query: {selenium_hub_url}")
    
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    default_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/138.0.7204.157 Safari/537.36'
    user_agent = os.environ.get('CHROME_USER_AGENT', default_user_agent)
    chrome_options.add_argument(f'user-agent={user_agent}')

    chrome_options.add_argument("--user-data-dir=/data")
    chrome_options.add_argument("--profile-directory=Default")

    try:
        browser = webdriver.Remote(
            command_executor=selenium_hub_url,
            options=chrome_options
        )
        browser.set_page_load_timeout(60)
        logger.info("WebDriver initialized successfully for query.")
        return browser
    except Exception as e:
        logger.error(f"Failed to initialize WebDriver for query: {e}", exc_info=True)
        return None

def find_element_by_priority(driver, selectors, condition=EC.presence_of_element_located, timeout=10):
    """
    Tries to find an element by iterating through a list of selectors.
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

@notebooklm_bp.route('/query', methods=['POST'])
def query_notebooklm():
    """
    Endpoint: Initializes a browser, submits a query to NotebookLM, and streams the response.
    The browser is closed after the query is complete.
    This is a stateless endpoint.
    """
    data = request.get_json() or {}
    if not data or 'query' not in data:
        return jsonify({'error': 'Missing "query" in request body'}), 400
    
    query_text = data['query']
    timeout = data.get('timeout', 180)
    notebooklm_url = data.get('notebooklm_url', "https://notebooklm.google.com/")

    def generate_response():
        browser_instance = initialize_browser_for_query()
        if not browser_instance:
            yield f'data: {json.dumps({"error": "Failed to initialize browser."})}\n\n'
            return

        try:
            # 1. Navigate and wait for page to load
            logger.info(f"Navigating to {notebooklm_url}...")
            browser_instance.get(notebooklm_url)
            logger.info(f"Navigation complete. Current URL: {browser_instance.current_url}")
            
            logger.info("Waiting for NotebookLM load indicators...")
            load_indicator = find_element_by_priority(browser_instance, NOTEBOOKLM_LOAD_INDICATORS, timeout=40)
            
            current_url = browser_instance.current_url
            if 'accounts.google.com' in current_url or 'signin' in current_url.lower():
                logger.warning("Redirected to a Google sign-in page. Aborting query.")
                yield f'data: {json.dumps({"error": "Redirected to Google sign-in page. Please ensure you are logged in to your Google account in the browser profile."})}\n\n'
                return
            elif not load_indicator:
                logger.error(f"Timed out waiting for NotebookLM interface to load at {notebooklm_url}.")
                yield f'data: {json.dumps({"error": f"Timed out waiting for NotebookLM interface to load at {notebooklm_url}."})}\n\n'
                return

            # Check if we are on a valid NotebookLM page
            if "notebooklm.google.com" not in current_url:
                logger.error(f"Navigation failed. Ended up at unexpected URL: {current_url}")
                yield f'data: {json.dumps({"error": f"Navigation failed. Expected a notebooklm.google.com URL, but ended up at {browser_instance.current_url}"})}\n\n'
                return

            # 2. Submit the query
            initial_response_count = len(browser_instance.find_elements(*RESPONSE_CONTENT_SELECTOR))
            
            logger.info("Attempting to find the chat input field...")
            input_field = find_element_by_priority(browser_instance, CHAT_INPUT_SELECTORS, condition=EC.element_to_be_clickable, timeout=10)
            if not input_field:
                logger.error("Failed to find the chat input field after 10 seconds.")
                logger.error("Failed to find the chat input field using XPath.")
                raise NoSuchElementException("Could not find the chat input field.")
            
            logger.info("Successfully found chat input field. Injecting query.")
            input_field.clear()
            input_field.send_keys(query_text)
            
            submit_button = find_element_by_priority(browser_instance, SUBMIT_BUTTON_SELECTORS, condition=EC.element_to_be_clickable, timeout=5)
            if submit_button:
                submit_button.click()
            else:
                input_field.send_keys(Keys.RETURN)
            
            logger.info("Query submitted, waiting for response from NotebookLM...")
            yield f'data: {json.dumps({"status": "waiting_for_response"})}\n\n'

            # 3. Stream the response
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
                    response_elements = browser_instance.find_elements(*RESPONSE_CONTENT_SELECTOR)
                    if len(response_elements) > initial_response_count:
                        response_element = response_elements[-1]
                        current_text = response_element.text
                        last_text = "" # Reset to re-send full content
                    else: # If we can't find it, break
                        break

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

        finally:
            if browser_instance:
                browser_instance.quit()
                logger.info("Browser instance for query has been closed.")

    return Response(stream_with_context(generate_response()), mimetype='text/event-stream')