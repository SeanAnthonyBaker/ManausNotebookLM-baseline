#!/bin/bash
# This script runs on VM startup

echo "Starting Selenium container and publishing ports..."

# Stop and remove any existing container with the same name to avoid conflicts on restart
docker stop selenium-hub &>/dev/null || true
docker rm selenium-hub &>/dev/null || true

# Pull the latest image and run it.
# The -p flags map the container ports to the host VM ports.
docker run -d --name selenium-hub \
  -p 4444:4444 \
  -p 7900:7900 \
  --shm-size="2g" \
  --restart=always \
  selenium/standalone-chrome:latest