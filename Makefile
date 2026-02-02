default: run

run:
	python -m main

lint:
	uv run ruff check . --fix

docker-up:
	docker compose -f ./deployment/docker-compose.yml -p aniscrape up -d --build

docker-down:
	docker compose -f ./deployment/docker-compose.yml -p aniscrape down