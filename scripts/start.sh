#!/bin/bash

# Start script for File Upload Service
set -e

echo "Starting File Upload Service..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "Please edit .env with your configuration and run again."
    exit 1
fi

# Create uploads directory
mkdir -p uploads

# Start services with docker-compose
echo "Starting services with Docker Compose..."
docker-compose up -d

echo "Waiting for services to be ready..."
sleep 10

# Check health
echo "Checking service health..."
curl -f http://localhost:8000/health || {
    echo "Service health check failed. Check logs:"
    docker-compose logs app
    exit 1
}

echo "✅ Service is running!"
echo "📋 API Documentation: http://localhost:8000/docs"
echo "🌸 Task Monitor: http://localhost:5555"
echo "🔍 Logs: docker-compose logs -f" 