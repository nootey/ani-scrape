COMPOSE       := -f ./deployment/docker-compose.yml
COMPOSE_BUILD := -f ./deployment/docker-compose.build.yml

# Docker targets pull the published image by default; pass build=1 to build from source instead
BUILD = $(if $(build),$(COMPOSE_BUILD))
FETCH = $(if $(build),--build,--pull always)

default: run

run:
	python -m main

lint:
	uv run ruff check . --fix

docker-up:
	docker compose $(COMPOSE) $(BUILD) up -d $(FETCH)

docker-down:
	docker compose $(COMPOSE) down
