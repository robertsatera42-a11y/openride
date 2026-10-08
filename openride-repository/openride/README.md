# OpenRide

OpenRide je česká webová aplikace pro komunitní spolujízdy. Obsahuje registraci s ověřením školního e-mailu, správu profilů a rolí, nabídky jízd, poptávky, rezervace, upozornění a mapy.

## Obsah složky

- `app/` – Django aplikace, databázové modely, migrace a testy
- `project/` – konfigurace Django projektu
- `templates/`, `static/` – české responzivní rozhraní
- `docker-compose.yml`, `Dockerfile` – běh aplikace a PostgreSQL
- `.env.example` – seznam konfiguračních proměnných bez tajných údajů

## Spuštění

Požadavky: Docker Engine s Compose pluginem. Zkopíruj `.env.example` na `.env`, vygeneruj vlastní `SECRET_KEY` a `DB_PASSWORD` a nastav `ALLOWED_HOSTS` a `CSRF_TRUSTED_ORIGINS` podle své adresy. `.env` nikdy neodesílej do Git repozitáře.

```sh
cp .env.example .env
docker compose up -d --build
```

Compose očekává externí Docker síť `web_proxy`, kterou musí vytvořit reverzní proxy. Databáze nemá veřejně publikovaný port. Pro samostatný lokální vývoj můžeš upravit `docker-compose.yml` a zpřístupnit aplikaci pouze na localhost.

Migrace databáze se spouštějí při startu. Stav aplikace ověří endpoint `/openride/health/`.

## E-mail a mapy

Pro aktivaci účtů nastav `BREVO_API_KEY` a ověřenou adresu `BREVO_FROM_EMAIL` v Brevo. Bez těchto údajů zůstávají nové účty neaktivní.

Pro mapové podklady, hledání míst a výpočet tras nastav `GEOAPIFY_SERVER_KEY`. Klíč se používá pouze na backendu. Omez ho v Geoapify na odchozí IP adresu serveru.

## Správce

Nejprve se běžným postupem zaregistruj a ověř školní e-mail. Potom spusť:

```sh
docker compose exec app python manage.py promote_admin uzivatel@opengate.cz
```

Příkaz povýší jen aktivní účet s ověřeným e-mailem `@opengate.cz` a odpovídajícím příjmením. Správcovská část aplikace je dostupná na `/openride/admin/`.

## Testy

```sh
docker compose run --rm app python manage.py test app
```

## Zálohování

`backup.sh` vytvoří komprimovanou zálohu databáze do `backups/`. `restore.sh` obnoví zvolený dump; obnova přepisuje aktuální databázi. Zálohy a produkční data nepatří do Git repozitáře.
