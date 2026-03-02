#!/bin/bash

# Billing V2 Docker Setup Script
# This script automates the initial Docker setup

set -e

echo "================================"
echo "Billing V2 - Docker Setup Script"
echo "================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "📋 Creating .env file from template..."
    cp .env.example .env
    echo "✅ .env created. Please review and update with your settings."
    echo "   Edit .env and change at minimum:"
    echo "   - DJANGO_SECRET_KEY"
    echo "   - DB_PASSWORD"
    echo "   - REDIS_PASSWORD"
    echo "   - BREVO_API_KEY (if using email)"
    echo ""
    read -p "Press Enter when you've updated .env..."
fi

# Check Docker and Docker Compose
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

echo "✅ Docker and Docker Compose found"
echo ""

# Build and start services
echo "🏗️  Building Docker images..."
docker-compose build --no-cache

echo ""
echo "🚀 Starting services..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check if services are up
if ! docker-compose exec -T db pg_isready &> /dev/null; then
    echo "⚠️  Database not ready yet, waiting..."
    sleep 10
fi

echo ""
echo "📊 Running migrations..."
docker-compose exec -T web python manage.py migrate

echo ""
echo "📁 Collecting static files..."
docker-compose exec -T web python manage.py collectstatic --noinput --clear

echo ""
echo "👤 Create superuser account"
read -p "Do you want to create a superuser now? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker-compose exec web python manage.py createsuperuser
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "🌐 Access your application:"
echo "   - Web App:        http://localhost:8000"
echo "   - Admin Panel:    http://localhost:8000/admin/"
echo "   - Flower Monitor: http://localhost:5555"
echo ""
echo "📚 Useful commands:"
echo "   - View logs:           docker-compose logs -f"
echo "   - Django shell:        docker-compose exec web python manage.py shell"
echo "   - Stop services:       docker-compose down"
echo "   - Restart services:    docker-compose restart"
echo ""
echo "📖 For more info, see DOCKER_DEPLOYMENT.md"
