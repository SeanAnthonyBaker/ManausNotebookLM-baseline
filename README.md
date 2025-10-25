# NotebookLM Automation System

This project provides a robust, containerized system for automating interactions with Google's NotebookLM. It features a dual-component architecture that separates stateful user management from stateless, resource-intensive browser automation tasks.

- **Stateful User API**: A RESTful API for CRUD operations on users, backed by a SQLite database.
- **Stateless Query API**: A powerful API that automates querying NotebookLM in a sandboxed browser for each request and streams the response back.

The entire system is designed for deployment in **Google Firebase Studio** and is defined declaratively using Nix for a reproducible environment.

## Key Features

- **Dual-Component Architecture**: Clear separation between a stateful User API and a stateless NotebookLM Query API.
- **Stateless & Sandboxed Queries**: Each query runs in a fresh, isolated browser session, ensuring reliability and preventing cross-request contamination. Resources are automatically cleaned up.
- **Intelligent Streaming**: The system doesn't just wait; it actively monitors the NotebookLM interface and streams the response back in real-time. It knows when the response is complete.
- **Dockerized**: The application and its dependencies are containerized with `docker-compose`, making setup and deployment consistent and straightforward.
- **Firebase Studio Ready**: Includes a `.idx/dev.nix` file for automatic, declarative environment setup in Firebase Studio.
- **Automation Bypass**: Implements techniques to appear as a regular user, reducing the risk of being blocked by Google's automation detection.

## System Architecture

The system consists of two main services managed by `docker-compose`:

1.  **Flask Application (`app`)**: A Python-based server that exposes the two APIs:
    *   **User API (`/api/users`)**: Manages user data in a persistent `app.db` SQLite file.
    *   **Query API (`/api/query`)**: Handles the browser automation. It communicates with the Selenium service to launch a Chrome browser, perform the query, and stream the results.
2.  **Selenium Service (`selenium`)**: Runs the `selenium/standalone-chrome` Docker image, providing the Chrome browser that the Flask application controls.

For session persistence (staying logged into Google), a local `./chrome-data` directory is mounted into the Selenium container. **This directory is in `.gitignore` to protect your session data.**

## Getting Started

### In Firebase Studio (Recommended)

1.  **Import the Project**: Import this Git repository into your Firebase Studio workspace.
2.  **Automatic Setup**: Firebase Studio will use the `.idx/dev.nix` file to automatically install all system dependencies (Python, Docker) and Python packages (`requirements.txt`).
3.  **Automatic Start**: The workspace is configured to automatically run `docker-compose up --build` on start, so the application will be running and ready.
4.  **Access**: Use the preview URL provided by Firebase Studio to access the application.

### Local Development

1.  **Prerequisites**: Ensure you have **Python 3.11+** and **Docker** (with `docker-compose`) installed.
2.  **Clone the Repository**:
    ```bash
    git clone <repository-url>
    cd <repository-directory>
    ```
3.  **Install Python Dependencies**:
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```
4.  **Run the Application**:
    ```bash
    docker-compose up --build
    ```
    The application will be running at `http://localhost:5000`.

**Important**: The first time you run the application, you may need to manually log in to your Google account within the Selenium container. You can do this using a VNC viewer to connect to the container's desktop.

## API Endpoints

### User API (Stateful)

- `GET /api/users`: Get a list of all users.
- `POST /api/users`: Create a new user.
  - **Body**: `{"username": "string", "email": "string"}`
- `GET /api/users/<id>`: Get a single user.
- `PUT /api/users/<id>`: Update a user.
- `DELETE /api/users/<id>`: Delete a user.

### NotebookLM Query API (Stateless)

- `POST /api/query`: Submits a query to NotebookLM and streams back the response.
  - **Body**: `{"query": "Your question..."}`
  - **Response**: A `text/event-stream` that you can consume to get the response in real-time.

#### Example with `curl`

```bash
# Create a user
curl -X POST -H "Content-Type: application/json" \
     -d '{"username": "testuser", "email": "test@example.com"}' \
     http://localhost:5000/api/users

# Query NotebookLM and see the live response
curl -N -X POST -H "Content-Type: application/json" \
     -d '{"query": "Explain the basics of machine learning."}' \
     http://localhost:5000/api/query
```
*(The `-N` flag in the second command is important to buffer the output and see the streaming.)*

## Troubleshooting

- **Authentication Errors**: If you get errors about being redirected to `accounts.google.com`, it means your session in the Selenium container has expired. You need to manually log in again via VNC.
- **UI Changes**: If NotebookLM's website structure changes, the Selenium selectors in `notebooklm.py` may need to be updated. This would typically result in `NoSuchElementException` errors.
- **Check the Logs**: The best way to debug is to check the container logs:
  ```bash
  docker-compose logs -f app
  docker-compose logs -f selenium
  ```
