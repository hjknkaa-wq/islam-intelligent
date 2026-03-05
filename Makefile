.RECIPEPREFIX := >

-include .env

INGEST_PORT ?= 8001

.PHONY: up down migrate ingest\:quran_sample ingest\:quran_full ingest\:hadith_full test logs

up:
>docker-compose up -d

down:
>docker-compose down

migrate:
>docker-compose exec api python /workspace/scripts/db_init.py --postgres

ingest\:quran_sample:
>python scripts/dev_reset_and_seed.py --quran-mode minimal

ingest\:quran_full:
>python scripts/dev_reset_and_seed.py --quran-mode tanzil --quran-variant uthmani

ingest\:hadith_full:
>python scripts/dev_reset_and_seed.py --quran-mode tanzil --quran-variant uthmani --hadith-mode api --hadith-all-supported-arabic --hadith-api-ref 1

test:
>PYTHONPATH=apps/api/src python -m pytest apps/api/tests -q

logs:
>docker-compose logs --tail=200
