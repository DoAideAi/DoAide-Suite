.PHONY: setup build dev worker backup test check scopes release-check
setup:
	uv sync --locked
	npm --prefix frontend ci
build:
	npm --prefix frontend run build
dev:
	uv run $(if $(wildcard .env),--env-file .env,) python scripts/dev.py
test:
	uv run pytest -q
check: test build
	npm --prefix frontend audit
scopes:
	uv run python scripts/build_scopes.py

worker:
	uv run $(if $(wildcard .env),--env-file .env,) python -m backend.worker
backup:
	uv run python scripts/backup.py
release-check:
	docker build --target runtime -t doaide-suite:release-validation .
	docker build --target ocr-worker -t doaide-suite-worker:release-validation .
	docker build -f deploy/clamav/Dockerfile -t doaide-suite-scanner:release-validation .
	uv run python scripts/check_production_stack.py
