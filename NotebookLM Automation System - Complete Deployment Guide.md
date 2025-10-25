# NotebookLM Automation System - Complete Deployment Guide

**Author:** Manus AI
**Date:** July 26, 2025
**Version:** 2.0

## Executive Summary

This document provides a comprehensive guide for deploying the NotebookLM Automation System. The system has been re-architected into a dual-component service designed for robustness and clarity, running within Docker containers on Google Firebase Studio.

The system now consists of:
1.  **A Stateful User Management API**: A standard RESTful service for creating, reading, updating, and deleting user records, backed by a persistent SQLite database.
2.  **A Stateless NotebookLM Query API**: A powerful, self-contained endpoint that, for each request, initializes a sandboxed browser, navigates to NotebookLM, submits a query, intelligently streams the complete response back, and securely terminates the session.

This guide covers system architecture, deployment on Firebase Studio, local development, API documentation, and production considerations.

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Prerequisites](#prerequisites)
3. [Firebase Studio Deployment](#firebase-studio-deployment)
4. [Local Development Setup](#local-development-setup)
5. [Docker Configuration](#docker-configuration)
6. [API Documentation](#api-documentation)
7. [Security and Automation Detection](#security-and-automation-detection)
8. [Monitoring and Troubleshooting](#monitoring-and-troubleshooting)
9. [Production Considerations](#production-considerations)
10. [Appendices](#appendices)

---

## 1. System Architecture

The system employs a microservices-oriented architecture, composed of two distinct services orchestrated by Docker Compose. This design separates the stateful user management from the stateless, resource-intensive browser automation tasks.

### Core Components

*   **Flask Application Server**: The central component, written in Python. It serves two distinct APIs:
    *   **User API (`/api/users`)**: A stateful CRUD interface for managing user data. It connects to a SQLite database (`app.db`) that persists user information across service restarts.
    *   **NotebookLM Query API (`/api/query`)**: A stateless endpoint that performs the browser automation. Each call to this endpoint is atomic and independent. It initiates a new Selenium browser session, performs the query, streams the result, and tears down the session. This stateless design enhances reliability and scalability, as there is no lingering browser state between requests.

*   **Selenium Standalone Chrome Container**: This service provides the necessary browser environment (Google Chrome) for the Flask application to perform its automation tasks. The Flask app communicates with this container over the internal Docker network to launch and control browser instances.

### Data Flow

*   **User Management**: A standard REST API flow. A client sends an HTTP request (e.g., `POST /api/users`) to the Flask app, which interacts with the SQLite database to perform the requested operation and returns a JSON response.
*   **NotebookLM Query**:
    1.  A client sends a `POST` request to `/api/query` with a query string.
    2.  The Flask application receives the request and initializes a new remote browser session in the Selenium container.
    3.  It navigates to NotebookLM, handling potential login pages by checking the URL. *Note: The user must be pre-authenticated in the browser profile used by Selenium.*
    4.  The query is submitted to the chat interface.
    5.  The application intelligently monitors the response area, waiting for the text to stop generating.
    6.  The response is streamed back to the client in real-time as `text/event-stream`.
    7.  Once the response is complete, the Flask application closes and quits the browser session, releasing all associated resources.

---

## 2. Prerequisites

*   **Firebase Studio Account**: Access to a Firebase Studio workspace.
*   **Technical Knowledge**: Basic understanding of Docker, `docker-compose`, REST APIs, and Python.
*   **Google Account**: An active Google account with access to NotebookLM. For the automation to work, you must be logged into your Google account within the Chrome profile that Selenium uses.

---

## 3. Firebase Studio Deployment

The project is configured for seamless setup on Firebase Studio via its `.idx/dev.nix` file.

### Automatic Environment Setup

Upon importing the project into Firebase Studio, the Nix configuration will automatically:
1.  Install system packages like `python3`, `pip`, and `docker-compose`.
2.  Install all Python dependencies from `requirements.txt`.
3.  Start the application services using `docker-compose` as defined in the `onStart` lifecycle hook.

### Manual Startup (If Needed)

If the automatic startup fails, you can run the services manually from the terminal:

```bash
# This command builds the Docker images and starts the Flask app and Selenium services.
docker-compose up --build
```

### Verification

*   **User API**:
    ```bash
    # Create a user
    curl -X POST -H "Content-Type: application/json" -d '''{"username": "test", "email": "test@test.com"}''' http://localhost:5000/api/users

    # Get users
    curl http://localhost:5000/api/users
    ```
*   **Query API**:
    ```bash
    # Query NotebookLM
    curl -N -X POST -H "Content-Type: application/json" -d '''{"query": "Explain quantum computing"}''' http://localhost:5000/api/query
    ```
    *(The `-N` flag for `curl` is important to see the streaming response).*

---

## 4. Local Development Setup

The local setup mirrors the Firebase Studio environment.

1.  **Install Dependencies**: Ensure you have Python 3.11+ and Docker with `docker-compose` installed on your local machine.
2.  **Set up Python Environment**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```
3.  **Run Services**:
    ```bash
    docker-compose up --build
    ```
    The application will be available at `http://localhost:5000`.

### Session Persistence (Google Login)

To avoid logging into Google on every container restart, the `docker-compose.yml` file maps a local `./chrome-data` directory into the Selenium container. This directory stores your Chrome profile, including cookies and session data.

*   **First-time setup**: You may need to use a VNC viewer to connect to the Selenium container to log in to your Google account manually. The VNC server is typically exposed by the Selenium container.
*   The `chrome-data` directory is in `.gitignore` to prevent committing sensitive session data.

---

## 5. Docker Configuration

The `docker-compose.yml` file orchestrates the two main services: `app` and `selenium`.

*   **`app` service**:
    *   Builds from the `Dockerfile` in the project root.
    *   Runs the Flask application (`main.py`).
    *   Maps port `5000` to the host for API access.
    *   Depends on the `selenium` service.
    *   Sets the `SELENIUM_HUB_URL` to communicate with the Selenium container.

*   **`selenium` service**:
    *   Uses the official `selenium/standalone-chrome` image.
    *   Maps the `./chrome-data` volume for persistent browser profiles.
    *   The browser inside this container is what the `app` service controls.

---

## 6. API Documentation

The API is split into two logical groups of endpoints.

### User API (Stateful)

These endpoints provide CRUD functionality for user management.

*   **`GET /api/users`**: Retrieves a list of all users.
*   **`POST /api/users`**: Creates a new user.
    *   **Body**: `{"username": "string", "email": "string"}`
    *   **Response**: The created user object or an error on conflict.
*   **`GET /api/users/<user_id>`**: Retrieves a single user by their ID.
*   **`PUT /api/users/<user_id>`**: Updates a user's information.
    *   **Body**: `{"username": "string", "email": "string"}` (both optional)
*   **`DELETE /api/users/<user_id>`**: Deletes a user.

### NotebookLM Query API (Stateless)

This is the core automation endpoint.

*   **`POST /api/query`**: Submits a query to NotebookLM and streams the response.
    *   **Request Body**:
        ```json
        {
          "query": "Your question for NotebookLM",
          "timeout": 180,
          "notebooklm_url": "https://notebooklm.google.com/"
        }
        ```
        *   `query` (required): The text to be submitted.
        *   `timeout` (optional, default: 180s): The total time to wait for the entire process.
        *   `notebooklm_url` (optional): The URL of the NotebookLM instance to query.
    *   **Response**:
        *   A `text/event-stream` which sends data chunks as they are generated by NotebookLM.
        *   Clients should listen for `data:` events. Each event contains a JSON string.
        *   **Event Types**:
            *   `{"status": "waiting_for_response"}`: Sent after the query is submitted.
            *   `{"status": "streaming"}`: The first chunk of the response is available.
            *   `{"chunk": "text content"}`: A piece of the response text.
            *   `{"status": "complete"}` or `{"status": "timeout"}`: The stream has finished.
            *   `{"error": "message"}`: An error occurred during the process.

---

## 7. Security and Automation Detection

*   **Automation Bypass**: The system uses specialized Chrome options and a modified user agent to appear as a standard user browser, reducing the chances of being blocked by Google's automation detection.
*   **Authentication**: The system does **not** handle passwords. It relies on a pre-authenticated Google session saved in the mounted `chrome-data` volume. If the session expires, the automation will fail until you manually log in again.
*   **Stateless Security**: The stateless nature of the `/api/query` endpoint is a security benefit. No browser instances are left dangling, and each request is isolated, reducing the risk of cross-request contamination.

---

## 8. Monitoring and Troubleshooting

*   **Docker Logs**: The primary source of information. Check the logs for both the `app` and `selenium` services.
    ```bash
    docker-compose logs -f app
    docker-compose logs -f selenium
    ```
*   **Common Issues**:
    *   **Redirect to Google Sign-in**: The most common issue. The automation will fail.
        *   **Symptom**: The API returns an error about being redirected to `accounts.google.com`.
        *   **Solution**: Manually log in to your Google Account. You may need a VNC client to access the Selenium container's desktop interface to do this.
    *   **Timeout Waiting for Interface**: The NotebookLM page is slow to load.
        *   **Symptom**: Error message "Timed out waiting for NotebookLM interface to load".
        *   **Solution**: Increase the `timeout` in the request body or check your network connection.
    *   **Element Not Found**: The selectors for the chat input or response area may have changed.
        *   **Symptom**: `NoSuchElementException`.
        *   **Solution**: This requires updating the Selenium selectors in the `notebooklm.py` source code.

---

## 9. Production Considerations

*   **Database**: The default SQLite database is suitable for single-node deployments but not for a horizontally scaled environment. For a multi-instance setup, migrate to a managed database like PostgreSQL or MySQL (e.g., Google Cloud SQL).
*   **Scalability**:
    *   The **User API** is a standard stateful web service.
    *   The **Query API** is stateless and CPU/memory intensive. It can be scaled horizontally, but each node will require its own Selenium service, or you can use a Selenium Grid for more advanced routing.
*   **Security Hardening**:
    *   Set `FLASK_ENV=production`.
    *   Use a strong, randomly generated `SECRET_KEY`.
    *   Restrict CORS origins to your frontend's domain.
*   **Disaster Recovery**: Regularly back up the user database. The `chrome-data` profile can be backed up but may contain sensitive session tokens.

---

## 10. Appendices

### Appendix A: API Response Example (`/api/query`)

A client consuming the streaming API would see a sequence of events like this:

```
data: {"status": "waiting_for_response"}

data: {"status": "streaming"}

data: {"chunk": "Quantum computing is a"}

data: {"chunk": " type of computation that"}

data: {"chunk": " harnesses the collective properties"}

data: {"chunk": " of quantum states..."}

...

data: {"status": "complete"}
```

### Appendix B: Key Configuration

*   **`main.py`**: Main Flask application setup.
*   **`notebooklm.py`**: Contains the logic for the `/api/query` endpoint and all Selenium selectors. This is the file to edit if the NotebookLM UI changes.
*   **`user.py`**: Contains the logic for the `/api/users` endpoints.
*   **`docker-compose.yml`**: Defines the services, networking, and volumes.
*   **`.idx/dev.nix`**: Defines the development environment for Firebase Studio.
