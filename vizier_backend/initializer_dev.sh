make cognito-env
docker compose exec web python manage.py flush --noinput
docker compose restart web