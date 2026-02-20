.PHONY: help build up down logs shell migrate test lint format clean cognito-env

help:
	@echo "Vizier Med Backend - Docker Commands"
	@echo "===================================="
	@echo ""
	@echo "Development:"
	@echo "  make build          Build Docker images"
	@echo "  make up             Start all services"
	@echo "  make down           Stop all services"
	@echo "  make logs           View logs (web service)"
	@echo "  make shell          Open Django shell"
	@echo "  make bash           Open bash shell in web container"
	@echo "  make cognito-env    Sync Cognito values from Terraform into .env"
	@echo ""
	@echo "Database:"
	@echo "  make migrate        Run Django migrations"
	@echo "  make migrations     Create new migrations"
	@echo "  make createsuperuser Create superuser"
	@echo "  make resetdb        Reset database (CAUTION!)"
	@echo ""
	@echo "Testing & Quality:"
	@echo "  make test           Run tests"
	@echo "  make coverage       Run tests with coverage"
	@echo "  make lint           Run linting (flake8)"
	@echo "  make format         Format code (black, isort)"
	@echo "  make check          Run all checks"
	@echo ""
	@echo "Production:"
	@echo "  make build-prod     Build production image"
	@echo "  make up-prod        Start production stack"
	@echo "  make down-prod      Stop production stack"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean          Remove containers and volumes"
	@echo "  make clean-all      Remove everything (CAUTION!)"

# Development
build:
	docker-compose build

up:
	docker-compose up -d
	@echo "Services started. Access at http://localhost:8000"

down:
	docker-compose down

logs:
	docker-compose logs -f web

logs-db:
	docker-compose logs -f db

logs-redis:
	docker-compose logs -f redis

shell:
	docker-compose exec web python manage.py shell

bash:
	docker-compose exec web bash

bash-root:
	docker-compose exec -u root web bash

# Database
migrate:
	docker-compose exec web python manage.py migrate

migrations:
	docker-compose exec web python manage.py makemigrations

createsuperuser:
	docker-compose exec web python manage.py createsuperuser

resetdb:
	@echo "WARNING: This will delete all data!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker-compose down -v; \
		docker-compose up -d; \
		docker-compose exec web python manage.py migrate; \
		echo "Database reset complete"; \
	fi

# Testing & Quality
test:
	docker-compose exec web python manage.py test

test-verbose:
	docker-compose exec web python manage.py test -v 2

test-specific:
	@read -p "Enter test path (e.g., apps.accounts.tests): " test_path; \
	docker-compose exec web python manage.py test $$test_path

coverage:
	docker-compose exec web coverage run --source='.' manage.py test
	docker-compose exec web coverage report
	docker-compose exec web coverage html
	@echo "Coverage report generated in htmlcov/index.html"

lint:
	docker-compose exec web flake8 apps/ vizier_backend/ services/ --max-line-length=120

format:
	docker-compose exec web black apps/ vizier_backend/ services/
	docker-compose exec web isort apps/ vizier_backend/ services/

check: lint test
	@echo "All checks passed!"

# Production
build-prod:
	docker build -f Dockerfile.prod -t vizier-med-backend:latest .
	@echo "Production image built: vizier-med-backend:latest"

up-prod:
	@if [ ! -f .env.prod ]; then \
		echo "ERROR: .env.prod not found. Create it from .env.example"; \
		exit 1; \
	fi
	docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d
	@echo "Production services started"

down-prod:
	docker-compose -f docker-compose.prod.yml down

logs-prod:
	docker-compose -f docker-compose.prod.yml logs -f web

# Cleanup
clean:
	docker-compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "Cleanup complete"

clean-all:
	@echo "WARNING: This will remove all Docker images, containers, and volumes!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		docker-compose down -v; \
		docker rmi vizier-med-backend:latest 2>/dev/null || true; \
		find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true; \
		find . -type f -name "*.pyc" -delete; \
		echo "Complete cleanup done"; \
	fi

# Utility
ps:
	docker-compose ps

inspect:
	docker-compose exec web python manage.py shell

collectstatic:
	docker-compose exec web python manage.py collectstatic --noinput

health:
	curl http://localhost:8000/api/health/

# Sync Terraform outputs into vizier_backend/.env
cognito-env:
	python3 scripts/sync_cognito_env_from_terraform.py --write

# Docker Hub / ECR
push-hub:
	@read -p "Enter Docker Hub username: " username; \
	docker tag vizier-med-backend:latest $$username/vizier-med-backend:latest; \
	docker push $$username/vizier-med-backend:latest; \
	echo "Pushed to Docker Hub"

push-ecr:
	@read -p "Enter AWS Account ID: " account_id; \
	@read -p "Enter AWS Region: " region; \
	aws ecr get-login-password --region $$region | docker login --username AWS --password-stdin $$account_id.dkr.ecr.$$region.amazonaws.com; \
	docker tag vizier-med-backend:latest $$account_id.dkr.ecr.$$region.amazonaws.com/vizier-med-backend:latest; \
	docker push $$account_id.dkr.ecr.$$region.amazonaws.com/vizier-med-backend:latest; \
	echo "Pushed to ECR"

# Development helpers
install-dev:
	pip install -r requirements.txt
	pip install pytest pytest-django coverage flake8 black isort

freeze:
	pip freeze > requirements-frozen.txt

update-deps:
	pip install --upgrade -r requirements.txt
