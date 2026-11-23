# Locust + Dynatrace PoC — Quickstart a demo pro pohovor

Tento návod popisuje **aktuální PoC**, nikoli plné cloudové nasazení. Příkazy spouštějte na Linuxu z kořene repozitáře. Ověřeno vůči konfiguraci na větvi `main` dne 2026-11-23; samotné příkazy z této stránky nebyly při tvorbě dokumentu vykonány na cílovém počítači.

Repozitář: https://github.com/Necraatall/secure-backend-platform  
Architektura, ADR a důkazy: [LOCUST_DYNATRACE_POC.md](LOCUST_DYNATRACE_POC.md)

## 1. Rozhodnutí, co předvést

| Režim | Potřebuje lokální backend? | Co dělá |
| --- | --- | --- |
| **Run GitHub** (doporučeno) | Ne | Lokální konfigurační UI spustí nové workflow na GitHub-hosted runneru, který samostatně vytvoří databázi a backend, provede test, uloží reporty a uklidí kontejnery. Dynatrace přijímá trace z CI backendu, pokud jsou připravena GitHub Secrets. |
| **Run** | Ano | Lokální UI spustí headless Locust proti `http://localhost:8000`; reporty vznikají lokálně. |
| **CLI** | Podle volby | Lokální `run.py` testuje lokální backend; `gh workflow run` spustí GitHub Actions bez webového UI. |

**Pozor:** `Run GitHub` není živý vzdálený Locust Web UI. Tlačítko `Stop` v konfiguračním UI zastavuje **pouze lokální** proces; není to vzdálené Stop pro GitHub Actions. Po skončení jobu GitHub runner končí.

## 2. Předpoklady a kontrola

- Ubuntu/Linux, Git, Python prostředí spravované přes `uv`.
- Pro lokální backend: funkční Docker Engine a Docker Compose plugin, přístup k Docker socketu.
- Pro `Run GitHub`: GitHub CLI `gh`, přihlášení a oprávnění spouštět workflow v tomto repozitáři.
- Pro zobrazení distribuovaných tras: přístup do příslušného Dynatrace tenantu. CI používá secrets `DT_API_TOKEN` a `DT_OTLP_TRACES_ENDPOINT`; pro samotný Locust test Dynatrace není povinný.
- Testovat jen vlastní/autorizované izolované prostředí se syntetickými daty.

```bash
cd ~/Programy/DevOps/secure-backend-platform
git status --short
git pull --ff-only

source .venv/bin/activate
uv sync --locked --group dev

uv --version
docker compose version
gh auth status
```

`git pull --ff-only` provádějte s čistým pracovním stromem a bez nechtěných lokálních změn. Na úplně novém klonu bez `.venv` stačí `uv sync --locked --group dev`, který vytvoří virtuální prostředí; případně následně `source .venv/bin/activate`.

`gh auth status` je potřebné pro GitHub režim, Docker pouze pro lokální backend. Na lokálním stroji **nevypisujte obsah `.env` ani tokenů** během screen-sharingu.

## 3. Nejsnazší prezentace — UI + Run GitHub (bez Dockeru)

**Terminál A, z kořene repozitáře:**

```bash
cd ~/Programy/DevOps/secure-backend-platform
source .venv/bin/activate

uv run --locked uvicorn ui:app \
  --app-dir performance/locust \
  --host 127.0.0.1 \
  --port 8501
```

Otevřete **http://127.0.0.1:8501** (ne `localhost`, kvůli kontrole Origin u lokálního UI).

V UI nastavte:
- **Hold**, **30 RPM**, **20 sekund**, **tolerance 20 %**.
- Klikněte **Run GitHub**; UI odešle `workflow_dispatch`, pokusí se dohledat stav a otevře odkaz na GitHub Actions.
- Workflow vytvoří **vlastní** FastAPI + PostgreSQL, vyčká na readiness, inicializuje databázi, ověří login, spustí Locust headless, nahraje HTML/CSV a provede cleanup.

**Terminál B — sledování běhu:**

```bash
gh run list \
  --repo Necraatall/secure-backend-platform \
  --workflow performance-locust.yml \
  --limit 3

# Nahraďte RUN_ID skutečným ID nového běhu.
gh run watch RUN_ID \
  --repo Necraatall/secure-backend-platform \
  --exit-status
```

Na GitHubu otevřete workflow [Performance Locust Manual](https://github.com/Necraatall/secure-backend-platform/actions/workflows/performance-locust.yml). V detailu běhu rozbalte **Upload Locust reports** a stáhněte artefakt `locust-hold-RUN_ID` s HTML/CSV reporty. Artefakty mají nastavenou **retenci 7 dní**.

**Záložní spuštění, pokud tlačítko Run GitHub nefunguje:**

```bash
gh workflow run performance-locust.yml \
  --repo Necraatall/secure-backend-platform \
  --ref main \
  -f profile=hold \
  -f rpm=30 \
  -f duration=20 \
  -f tolerance_pct=20
```

Už ověřený referenční běh: [44960706592](https://github.com/Necraatall/secure-backend-platform/actions/runs/44960706592), commit `f8dbadd`, Hold 30 RPM/20 s, všechny workflow kroky PASS. Běh byl spuštěn přes `gh workflow run`; to **není** samostatný důkaz bezchybnosti tlačítka UI.

## 4. Dynatrace — důkaz konkrétního běhu

Otevřete [Distributed Tracing Explorer](https://oal44442.apps.dynatrace.com/ui/apps/dynatrace.distributedtracing/explorer?v=transactions) a nastavte časový rozsah pokrývající dokončený test.

- Vyhledejte service `secure-backend-platform`.
- Filtrujte resource atribut `ci.github.run_id` podle skutečného **RUN_ID**, například `44960706592`.
- Alternativně hledejte `deployment.environment.name = github-actions`.
- Otevřete requesty pro login, items a simulovanou platbu. HTTP 401/403 u negativních případů může být **očekávaný** výsledek.
- Rozlišujte tři věci: úspěšný CI běh, úspěšný Locust scénář a skutečně přijatý trace. Jedno **nedokazuje automaticky** druhé.

V referenčním běhu `44960706592` byl z Dynatrace Exploreru doložen filtr `ci.github.run_id` a **15 transakcí**. To není důkaz kompletního pokrytí všech negativních scénářů. Lokální FastAPI může emitovat trace se stejným `service.name`, ale bez tohoto GitHub run ID.

## 5. Volitelně — lokální FastAPI + PostgreSQL a tlačítko Run

**Nejdřív zkontrolujte soubor `.env`** (neukazujte ho na projektoru). Musí obsahovat platné hodnoty pro Docker Compose a testovací přihlášení, zejména `PROJECT_NAME`, `SECRET_KEY`, `POSTGRES_PASSWORD`, `FIRST_SUPERUSER`, `FIRST_SUPERUSER_PASSWORD` a `EMAILS_FROM_EMAIL`. Když `.env` chybí, lze vyjít z `.env.example` a hodnoty upravit; ukázkové přihlašovací údaje nejsou určeny do veřejného prostředí. Lokální Dynatrace je volitelný (případně `DT_TRACING_ENABLED=true` a soukromé `DT_OTLP_TRACES_ENDPOINT` / `DT_API_TOKEN`).

**Terminál B, lokální backend:**

```bash
cd ~/Programy/DevOps/secure-backend-platform
source .venv/bin/activate

docker compose up -d --build db backend
docker compose run --rm backend bash scripts/prestart.sh

curl -i http://127.0.0.1:8000/api/v1/utils/health-check/
docker compose ps
```

Očekávaný healthcheck: **HTTP 200**. Iniciační skript provede databázové migrace a vytvoří počáteční data / superuživatele.

V již otevřeném konfiguračním UI (terminál A, port 8501) vyberte **Hold**, **30 RPM**, **20 sekund**, **20 % tolerance** a klikněte **Run**. Lokální `Stop` ukončuje lokální proces. Reporty z tohoto běhu najdete v:

```text
performance/reports/hold.html
performance/reports/hold_stats.csv
performance/reports/hold_stats_history.csv
performance/reports/hold_failures.csv
performance/reports/ui_run.log
```

Alternativa bez UI:

```bash
uv run --locked python performance/locust/run.py hold \
  --rpm 30 \
  --duration 20 \
  --tolerance-pct 20
```

Runner používá `http://localhost:8000` a čte autentizační údaje z `.env`. Tento konkrétní režim je **headless**; neotevírá automaticky Locust Web UI na portu 8089.

## 6. Ukončení

- UI server v terminálu A: **Ctrl+C**.
- Lokální Locust běh: tlačítko **Stop** v UI, nebo vyčkat na dobu testu.
- Lokální Docker kontejnery (jen pokud jste je spouštěli v kroku 5):

```bash
docker compose down
docker compose ps
```

`docker compose down` bez `-v` neodstraňuje pojmenované databázové volumes. **Nezastavuje Docker službu jako celek.** GitHub Actions job naopak po dokončení sám provádí `docker compose down -v --remove-orphans` ve vlastním izolovaném runneru. Trvale připravená cloudová testovací instance v současném PoC **neexistuje**.

## 7. Diagnostika

| Projev | Kontrola / řešení |
| --- | --- |
| Port 8501 je obsazený | `ss -ltnp | grep ':8501'`; nevytvářet druhou UI instanci na jiném portu bez úpravy kontroly Origin. |
| `gh` nelze spustit / není autorizovaný | `gh auth status`, ověřit přístup k repozitáři a právo spouštět Actions. |
| UI hlásí `GitHub FAIL` | Podívat se na text chyby v UI; zkusit záložní `gh workflow run`. UI dispatch na čistém checkoutu ještě není samostatně end-to-end akceptován. |
| `Run GitHub` nevyvolal nový běh | `gh run list --workflow performance-locust.yml --limit 3`; ověřit, zda je UI server spuštěn s aktuálním kódem. |
| Local Run: chyby přihlášení | Zkontrolovat `.env` a inicializaci DB, nevyzrazovat hesla v logu či na screenshotu. |
| Docker není dostupný | `docker info` a `docker compose ps`; zkontrolovat běh Docker služby a práva. |
| HTTP 8000 nedostupné | `docker compose ps` a `docker compose logs --tail 80 backend`; případně konflikt portu 8000. |
| Dynatrace nezobrazuje trace | Zkontrolovat časový rozsah, správný run ID, přístup do tenantu; u CI status kroku `Start isolated backend` a nastavení GitHub Secrets. **Nezveřejňovat token**. |
| Spousta healthcheck trace | Docker backend má `healthcheck` každých 10 s po dobu života kontejneru; není to běžící či čekající CI pipeline. |
| `Hold + Bell` v UI nelze spustit | Známý nesoulad: UI používá identifikátor `hold-bell`, zatímco `Profile` enum v `config.py` definuje `hold_bell`. Profil v CI byl ověřen, ale UI cesta pro tuto volbu vyžaduje opravu a nový test. |

## 8. Krátký scénář pro pohovor (cca 5 minut)

1. Otevřít konfigurační UI a vysvětlit čtyři **návrhy profilů zátěže**.
2. Nastavit Hold 30 RPM / 20 s a ukázat graf plánovaného průběhu.
3. Spustit `Run GitHub`, případně fallback přes `gh workflow run`.
4. Na GitHubu ukázat startup backendu, healthcheck, Locust, artifacts a cleanup.
5. V Dynatrace filtrovat skutečné `ci.github.run_id` a ukázat trasování login/items/payment.
6. V [ADR](LOCUST_DYNATRACE_POC.md) vysvětlit, proč zatím používáme dočasný runner místo stále běžící infrastruktury.

**Scope:** PoC je předveditelný, ale není to produkční platforma, public remote dashboard, výkonnostní garance ani doklad úplné funkční coverage API scénářů.
