# 🤖 NotebookLM Automation API

A re-architected, dual-component system for automating Google NotebookLM, designed for reliability and clarity. It runs in Docker containers and is optimized for Google Firebase Studio.

## 🌟 Core Architecture

The system is now composed of two distinct services:

1.  **Stateful User API**: A standard RESTful API for Creating, Reading, Updating, and Deleting (CRUD) user data, which is persisted in a SQLite database.
2.  **Stateless NotebookLM Query API**: A single, robust endpoint (`/api/query`) that performs the entire browser automation lifecycle for each request. It is self-contained, sandboxed, and leaves no lingering state.

## 🚀 Quick Start

### In Firebase Studio (Recommended)

1.  **Import this Git repository** into a Firebase Studio workspace.
2.  **Wait for Automatic Setup**: Firebase Studio will use `.idx/dev.nix` to install all dependencies and then use `docker-compose` to start the services.
3.  **Access the application** via the preview URL provided by Firebase Studio.

### Local Docker Setup

1.  **Prerequisites**: Install **Python 3.11+** and **Docker** with `docker-compose`.
2.  **Clone and set up**:
    ```bash
    git clone <repository-url>
    cd <repository-directory>
    ```
3.  **Start the services**:
    ```bash
    docker-compose up --build
    ```
4.  **Access the application** at `http://localhost:5000`.

## 📋 API Endpoints

The API is now logically separated into two distinct groups.

### 1. User API (Stateful)

Provides standard CRUD operations for users.

- **`GET /api/users`**: Get a list of all users.
- **`POST /api/users`**: Create a new user.
  - **Body**: `{"username": "new-user", "email": "user@example.com"}`
- **`GET /api/users/<id>`**: Get a single user by ID.
- **`PUT /api/users/<id>`**: Update a user's details.
- **`DELETE /api/users/<id>`**: Delete a user.

### 2. NotebookLM Query API (Stateless)

This single endpoint handles all browser automation.

- **`POST /api/query`**: Submits a query to NotebookLM and streams the response back.
  - **Body**: `{"query": "Your question for NotebookLM..."}`

**Streaming Response:**

The response is a `text/event-stream` that sends JSON objects. You will receive a sequence of events like:

1.  `{"status": "waiting_for_response"}`
2.  `{"status": "streaming"}`
3.  `{"chunk": "The first part of the answer..."}`
4.  `{"chunk": "...the next part..."}`
5.  `{"status": "complete"}` (or `timeout` / `error`)

#### Example: Using `curl` to Query

```bash
# Use the -N flag to see the streaming response as it comes in
curl -N -X POST -H "Content-Type: application/json" \
     -d '{"query": "Explain the theory of relativity in simple terms."}' \
     http://localhost:5000/api/query
```

## 🐳 Docker Architecture

The `docker-compose.yml` file defines two services:

```
┌─────────────────────┐       ┌──────────────────────┐
│   Flask API (`app`) │       │  Selenium (`selenium`)│
│  - Serves API       │──────▶│ - Runs Chrome Browser  │
│  - Manages DB       │       │ - Exposes WebDriver    │
└─────────────────────┘       └──────────────────────┘
```

- The **`app`** service runs the Python Flask application.
- The **`selenium`** service provides the browser that the `app` service controls.
- A local `./chrome-data` volume is mounted to persist your Google login session.

## 🔒 Security & Automation

- **Stateless by Design**: The query endpoint is stateless, meaning each request is completely isolated. This greatly improves security and reliability, as there are no shared browser sessions between queries.
- **Automation Bypass**: Uses carefully selected Chrome options and a realistic user agent to avoid being flagged as a bot.
- **Authentication**: Relies on a pre-authenticated Google session stored in the `chrome-data` volume. It will detect if a login is required and return an error, but it does not handle credentials itself.

## 📊 Monitoring & Debugging

- **Primary Tool**: Use Docker logs to see what's happening.
  ```bash
  # View logs for the app
  docker-compose logs -f app

  # View logs for the browser container
  docker-compose logs -f selenium
  ```
- **Common Problem**: `Redirected to Google sign-in` error.
  - **Cause**: The Google session in your `chrome-data` volume has expired.
  - **Fix**: You must re-authenticate. This may require using a VNC viewer to interact with the browser inside the Selenium container.

## 🚀 Deployment

- **Environment**: For production, set the `FLASK_ENV` environment variable to `production` and use a strong `SECRET_KEY`.
- **Database**: The default SQLite database is not suitable for multi-server scaling. For larger deployments, switch to a production-grade database like PostgreSQL.
- **Scaling**: The stateless `/api/query` endpoint can be scaled horizontally. Each instance would require its own Selenium setup, or you could use a central Selenium Grid.
