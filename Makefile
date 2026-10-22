.PHONY: up down dev-infra api worker web test test-web eval types migrate fmt

up:            ## Run the whole stack
	docker compose up --build

down:
	docker compose down

dev-infra:     ## Only Postgres + Redis + MinIO (for running api/web locally)
	docker compose up -d postgres redis minio

migrate:
	cd backend && alembic upgrade head

api:
	cd backend && uvicorn stylelens.api.main:app --reload --port 8000

worker:
	cd backend && arq stylelens.worker.settings.WorkerSettings --watch stylelens

web:
	cd frontend && npm run dev

test:
	cd backend && python -m pytest -q

test-web:
	cd frontend && npm run typecheck && npm run lint

eval:          ## Retrieval / answer / comparison evaluation on the golden set
	cd backend && python -m stylelens.eval.run

types:         ## Regenerate TypeScript API types from the running API
	cd frontend && npm run gen:types
