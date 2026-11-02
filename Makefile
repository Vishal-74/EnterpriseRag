.PHONY: db db-stop migrate test lint api web install

db:
	docker compose up -d db

db-stop:
	docker compose down

install:
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install -r backend/requirements.txt -r backend/requirements-dev.txt
	cd frontend && npm install

migrate:
	cd backend && .venv/bin/alembic upgrade head

test:
	cd backend && .venv/bin/pytest

lint:
	cd backend && .venv/bin/ruff check app tests eval scripts && .venv/bin/ruff format --check app tests eval scripts && .venv/bin/mypy app
	cd frontend && npm run lint

api:
	cd backend && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

web:
	cd frontend && npm run dev
