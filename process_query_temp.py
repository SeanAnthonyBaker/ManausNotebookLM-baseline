@notebooklm_bp.route('/process_query', methods=['POST'])
def process_query():
    """
    Consolidated Endpoint: Opens NotebookLM, submits a query, streams the response, and closes the browser.
    """
    data = request.get_json()
    if not data or 'query' not in data:
        return jsonify({'error': 'Missing "query" in request body'}), 400
    
    url = data.get('notebooklm_url', "https://notebooklm.google.com/")
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

                # For notebook pages, just look for chat input directly
                logger.info("Looking for chat input to confirm page is ready...")
                load_indicator = find_element_by_priority(browser_instance, CHAT_INPUT_SELECTORS, timeout=30)
                if not load_indicator:
                    logger.error(f"Timed out waiting for chat input. Current URL: {browser_instance.current_url}")
                    yield f'data: {json.dumps({"error": "Timed out waiting for NotebookLM interface."})}\n\n'
                    return
                else:
                    logger.info("Chat input found, interface ready.")
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
