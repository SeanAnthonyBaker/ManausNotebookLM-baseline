#!/bin/bash

# NotebookLM Automation Docker Startup Script
# This script starts the Selenium Chrome container and Flask API

set -e

echo "🚀 Starting NotebookLM Automation Services..."

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed. Please install docker-compose first."
    exit 1
fi

# --- Pre-flight check and creation of environment file ---
if [ ! -f ".env" ]; then
    echo "⚠️  [INFO] The .env file was not found. Creating one from .env.example."
    cp .env.example .env

    # Generate a random secret key and replace the placeholder.
    # Use openssl if available, otherwise a simple fallback.
    if command -v openssl &> /dev/null; then
        SECRET_KEY=$(openssl rand -hex 32)
    else
        # A simpler but effective fallback for environments without openssl
        SECRET_KEY=$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 64)
    fi

    # Use sed to replace the key. The use of a different delimiter avoids issues with special characters.
    sed -i "s|your-super-secret-key-here|$SECRET_KEY|" .env
    echo "✅ A new .env file has been created with a generated FLASK_SECRET_KEY."
    echo "   [ACTION] Please review the .env file and set CHROME_PROFILE_GCS_PATH if you plan to use session persistence."
    echo ""
fi

# --- Pre-flight check for the gcloud credentials directory ---
if [ ! -d ".gcloud" ]; then
    echo "❌ [ERROR] The .gcloud credentials directory was not found in your project root."
    echo "   [INFO]  Please create the '.gcloud' directory and copy your gcloud credential files into it."
    exit 1
fi

# A more specific check for the ADC file, which is crucial for authentication.
if [ ! -f ".gcloud/application_default_credentials.json" ]; then
    echo "❌ [ERROR] The gcloud credential file ('application_default_credentials.json') was not found inside the '.gcloud' directory."
    echo "   [INFO]  Please run 'gcloud auth application-default login' in your terminal to generate it."
    echo "   [INFO]  Then, copy the credentials from '~/.config/gcloud/' into your project's '.gcloud' directory."
    exit 1
fi

# Check if a quota project is set in the ADC file, which is required for GCS operations.
if ! grep -q "quota_project_id" ".gcloud/application_default_credentials.json"; then
    echo "⚠️  [WARNING] Your Google Application Default Credentials do not have a quota project set."
    echo "   [INFO]    This can cause issues when accessing Google Cloud services like GCS."
    echo "   [ACTION]  Run the following command in your terminal, replacing 'your-gcp-project-id' with your actual project ID:"
    echo "             gcloud auth application-default set-quota-project your-gcp-project-id"
    echo "   [INFO]    Then, copy the updated 'application_default_credentials.json' file into the '.gcloud' directory."
    echo "             Continuing in 5 seconds..."
    echo ""
    sleep 5
fi

# Stop any existing containers
echo "🛑 Stopping existing containers..."
docker-compose down --remove-orphans

# Build and start the services
echo "🔨 Building and starting services..."
docker-compose up --build -d

# Wait for services to be healthy
echo "⏳ Waiting for services to become healthy..."

for i in {1..30}; do
    # Check if selenium is healthy
    selenium_id=$(docker-compose ps -q selenium)
    if [ -n "$selenium_id" ] && [ "$(docker inspect -f '{{.State.Health.Status}}' "$selenium_id" 2>/dev/null)" = "healthy" ]; then
        # Now check if the app is healthy
        app_id=$(docker-compose ps -q app)
        if [ -n "$app_id" ] && [ "$(docker inspect -f '{{.State.Health.Status}}' "$app_id" 2>/dev/null)" = "healthy" ]; then
            break
        fi
    fi
    echo -n "."
    sleep 2
done

if [ "$i" -eq 30 ]; then
    echo ""
    echo "❌ One or more services failed to become healthy in time."
    echo "📊 Final service status:"
    docker-compose ps
    echo "🪵 To see detailed logs, run: docker-compose logs -f"
    exit 1
fi

echo "" # Newline for cleaner output
echo "✅ All services are healthy and running!"
echo "📋 Service URLs:"
echo "   • Flask API: http://localhost:5000"
echo "   • API Status: http://localhost:5000/api/status"
echo "   • Selenium Hub: http://localhost:4444"
echo "   • VNC Viewer: http://localhost:7900 (password: secret)"
echo ""
echo "💡 Note: To access these from your browser, use the preview URLs provided by Firebase Studio for each port."
