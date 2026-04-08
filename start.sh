#!/bin/bash
# Start all SpeedReader services

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

source venv/bin/activate

cleanup() {
    echo "Shutting down..."
    kill $DJANGO_PID $CELERY_PID 2>/dev/null
    wait $DJANGO_PID $CELERY_PID 2>/dev/null
    echo "All services stopped."
    exit 0
}
trap cleanup SIGINT SIGTERM

# Start Redis if not running
if ! redis-cli ping &>/dev/null; then
    echo "Starting Redis..."
    sudo service redis-server start
fi

# Start MySQL if not running
if ! mysqladmin ping -u root --silent &>/dev/null; then
    echo "Starting MySQL..."
    sudo service mysql start
fi

# Start Celery worker
echo "Starting Celery worker..."
celery -A config worker --loglevel=info &
CELERY_PID=$!

# Start Django dev server
echo "Starting Django server on http://localhost:8000..."
python manage.py runserver 0.0.0.0:8000 &
DJANGO_PID=$!

echo "All services running. Press Ctrl+C to stop."
wait
