.PHONY: up down
up:
	docker compose up --build -d
down:
	docker compose down

# Isolated credential-free stack on separate ports, including its own SQLite volume.
DEMO = env ENABLE_FAILURE_SIMULATION=true FRONTEND_PORT=3100 BACKEND_PORT=8100 VITE_API_BASE_URL=http://localhost:8100 ALLOWED_ORIGINS=http://localhost:3100 docker compose -p lyftr-acceptance -f docker-compose.yml -f backend/tests/stack/compose.yml
.PHONY: demo demo-down
demo:
	$(DEMO) up --build -d
demo-down:
	$(DEMO) down
