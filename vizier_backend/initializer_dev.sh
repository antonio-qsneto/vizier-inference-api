make cognito-env
docker compose exec web python manage.py flush
docker compose restart web