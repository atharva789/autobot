.PHONY: dev test smoke-api smoke-morph smoke-gnn smoke-seed e2e-smoke

dev:
	uvicorn demo.app:app --reload &
	cd apps/web && npm run dev

test:
	python -m pytest tests/ -q --timeout=60

smoke-api:
	python -m pytest tests/test_api.py tests/test_evolutions.py tests/test_ingest.py -q

smoke-morph:
	python -m pytest tests/test_morphology.py -q

smoke-gnn:
	python -m pytest tests/test_gnn.py -q

smoke-seed:
	python -m pytest tests/test_seed.py -q

e2e-smoke:
	python tests/e2e_smoke.py
