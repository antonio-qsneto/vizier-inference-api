#!/bin/bash

set -e

echo "Starting Vizier Med Backend..."

# Wait for database to be ready
echo "Waiting for database..."
while ! nc -z db 5432; do
  sleep 0.1
done
echo "Database is ready!"

# Wait for Redis to be ready
echo "Waiting for Redis..."
while ! nc -z redis 6379; do
  sleep 0.1
done
echo "Redis is ready!"

# Run migrations
echo "Running migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Create superuser if it doesn't exist
if [ "$CREATE_SUPERUSER" = "true" ]; then
    echo "Creating superuser..."
    python manage.py shell << END
from django.contrib.auth import get_user_model
from apps.tenants.models import Clinic
User = get_user_model()

if not User.objects.filter(email='admin@viziermed.com').exists():
    # Create clinic first
    clinic, _ = Clinic.objects.get_or_create(
        name='Admin Clinic',
        defaults={'cnpj': '00000000000191'}
    )
    
    # Create superuser
    User.objects.create_superuser(
        email='admin@viziermed.com',
        cognito_sub='admin-cognito-sub',
        password='${SUPERUSER_PASSWORD:-admin123}',
        first_name='Admin',
        last_name='User',
        clinic=clinic
    )
    print("Superuser created successfully!")
else:
    print("Superuser already exists!")
END
fi

# Start the application
echo "Starting application..."
exec "$@"
