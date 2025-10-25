# Firebase Studio Deployment Guide

## 🚀 Deploying the NotebookLM Automation System in Firebase Studio

This guide provides step-by-step instructions for setting up and deploying the NotebookLM Automation system within a Google Firebase Studio workspace.

The application consists of two main components:
1.  **A Stateful User Management API**: A standard RESTful service for creating, reading, updating, and deleting user records, backed by a SQLite database.
2.  **A Stateless NotebookLM Query API**: A service that uses Selenium to automate queries against the NotebookLM interface and streams the results back to the client.

## 📋 Prerequisites

*   A Google Account with access to [Firebase Studio](https://firebase.studio/).
*   A Firebase Studio workspace.
*   A basic understanding of Flask, Docker, and REST APIs.

## 🔧 Environment Setup in Firebase Studio

The project is designed to be set up automatically by Firebase Studio using the `.idx/dev.nix` configuration file. When you import the project, Firebase Studio will:

1.  **Install Required Packages**: Automatically install `python3`, `pip`, and other necessary system-level dependencies defined in `dev.nix`.
2.  **Install Python Dependencies**: Run `pip install -r requirements.txt` to install all the necessary Python libraries for the Flask application.
3.  **Start Services**: Automatically run the startup commands defined in the `onStart` lifecycle hook, which typically involves starting the Selenium service and the Flask application.

## 🚀 Running the Application

The application requires two services to be running simultaneously:

1.  **Selenium Chrome Node**: A Docker container that provides a remote-controlled browser for the application to use.
2.  **Flask Web Server**: The main Python application that serves the API endpoints.

These services are managed by `docker-compose.yml`. To start everything, run:

```bash
docker-compose up --build
```

This command will build the application's Docker image and start both the `app` (your Flask server) and the `selenium` service.

## ✅ Testing the Deployment

Once the services are running, you can test the different parts of the API.

### 1. Test the User Management API (Stateful)

You can use `curl` to interact with the user endpoints:

```bash
# Create a new user
curl -X POST -H "Content-Type: application/json" -d '{"username": "testuser", "email": "test@example.com"}' http://localhost:5000/api/users

# Get all users
curl http://localhost:5000/api/users
```

### 2. Test the NotebookLM Query API (Stateless)

This endpoint streams the response.

```bash
# Send a query and get a streaming response
curl -X POST -H "Content-Type: application/json" \
     -d '{"query": "What is the capital of France?"}' \
     http://localhost:5000/api/query
```

### 3. Access the Web Interface

The project serves a static web interface. You can open it using Firebase Studio's preview feature, which will point to the root of the running application.

## ☁️ Deployment to Production (Google Cloud Run)

Deploying this application requires deploying both the Flask app and the Selenium service.

### Step 1: Containerize the Application

The included `Dockerfile` and `docker-compose.yml` are already set up for containerization.

### Step 2: Push Images to a Registry

Push the application and Selenium images to a container registry like Google Artifact Registry.

```bash
# Authenticate with Google Cloud
gcloud auth configure-docker

# Tag and push the app image
docker tag notebooklm-app gcr.io/your-gcp-project-id/notebooklm-app:latest
docker push gcr.io/your-gcp-project-id/notebooklm-app:latest

# Note: The Selenium image is public, so you don't need to push it yourself.
```

### Step 3: Deploy to Cloud Run

1.  **Deploy the Selenium Service**:
    *   Deploy the `selenium/standalone-chrome:latest` image as a private Cloud Run service.
    *   Take note of the internal URL it is given (e.g., `selenium-service-xxxx.a.run.app`).

2.  **Deploy the Flask Application**:
    *   Deploy your `notebooklm-app` image to Cloud Run.
    *   Set the `SELENIUM_HUB_URL` environment variable to point to your deployed Selenium service's URL (e.g., `http://selenium-service-xxxx.a.run.app/wd/hub`).
    *   Ensure other environment variables like `FLASK_ENV=production` and `SECRET_KEY` are set.
    *   This service should be configured to allow public access so users can reach your API.

## 🔧 Firebase Studio `dev.nix` Configuration

The `.idx/dev.nix` file is the heart of the environment's configuration.

```nix
{ pkgs, ... }: {
  # Use a stable channel for Nix packages
  channel = "stable-23.11";

  # Install Python and Pip
  packages = [
    pkgs.python311
    pkgs.python311Packages.pip
  ];

  # Workspace lifecycle hooks
  idx.workspace = {
    # On workspace creation, install dependencies
    onCreate = {
      install-deps = "pip install -r requirements.txt";
    };
    # On workspace start, launch the services
    onStart = {
      start-services = "docker-compose up --build";
    };
  };

  # Configure a web preview for the Flask app
  idx.previews = {
    enable = true;
    previews = {
      web = {
        command = ["python" "main.py"];
        manager = "web";
      };
    };
  };
}
```

## 🔒 Security Considerations

*   **Production Environment**: Always set `FLASK_ENV=production` in a production environment.
*   **Secret Key**: Use a strong, unique `SECRET_KEY` for session management.
*   **Database**: The default SQLite database is not recommended for a scalable production environment. Consider migrating to a managed database like Google Cloud SQL.
*   **CORS**: The `flask_cors` extension is configured to allow all origins. For production, you should restrict this to your specific frontend domain.

---

**Note**: This guide assumes a deployment target like Google Cloud Run that can run Docker containers. Adjust the deployment steps as needed for your chosen platform.
