.RECIPEPREFIX := >

-include .env

INGEST_PORT ?= 8001

.PHONY: up down migrate ingest\:quran_sample test logs

up:
>docker-compose up -d

down:
>docker-compose down

migrate:
>docker-compose exec api python /workspace/scripts/db_init.py --postgres

ingest\:quran_sample:
>python -c "import json, urllib.request; payload = json.dumps({'source_type': 'quran_sample', 'payload': {'fixture': 'data/fixtures/quran_minimal.yaml'}}).encode('utf-8'); req = urllib.request.Request('http://localhost:$(INGEST_PORT)/ingest', data=payload, headers={'Content-Type': 'application/json'}); print(urllib.request.urlopen(req).read().decode('utf-8'))"

test:
>PYTHONPATH=apps/api/src python -m pytest apps/api/tests -q

logs:
>docker-compose logs --tail=200
