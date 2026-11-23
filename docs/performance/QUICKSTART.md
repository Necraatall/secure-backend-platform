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

## 3. Přehled aplikací: co je původní Locust a co je vlastní UI

| Komponenta | Jak ji otevřít | Co umí | Co neumí |
| --- | --- | --- | --- |
| **FastAPI + PostgreSQL** | Docker Compose; API `http://127.0.0.1:8000` | Cílový backend testů, autentizace, položky, syntetické platby | Není samo o sobě dashboard zátěže |
| **Původní Locust Web UI** | Spustit příkaz v kapitole 6; `http://127.0.0.1:8089` | Vestavěný Locust dashboard: počet virtuálních uživatelů, spuštění a zastavení zátěže, živé statistiky a grafy, failure data | Neslouží k odesílání našeho GitHub workflow a neovládá izolovaný runner |
| **Moje vlastní Locust Performance Control UI** (`performance/locust/ui.py`) | `http://127.0.0.1:8501` | Volba profilu Hold/Bell/Hold + Bell/Recovery; nastavení RPM/RPS, baseline, času fází a tolerance; graf **plánovaného** zatížení; `Run`, `Stop`, `Run GitHub`; stav běhu a odkaz na GitHub | Graf není živě měřená křivka výkonu. `Stop` ovládá jen lokální test, ne GitHub job. Není to vzdálený dashboard Locustu |
| **Dynatrace SaaS** | Otevřít webový odkaz v kapitole 8; přihlásit se do tenantu | Přijímá OpenTelemetry trace z FastAPI, zobrazuje trasy a HTTP endpointy; GitHub běhy lze filtrovat podle `ci.github.run_id` | Není lokálně spouštěný proces ani náhrada Locust reportů |

### Vlastní UI — proč jsem ho vytvořil a jak funguje

Vestavěné UI Locustu je vhodné pro řízení a sledování **lokálně spuštěného Locustu**. Samostatně jsem vytvořil malou konfigurační aplikaci ve **FastAPI + HTML/JavaScript**, aby bylo možné předem sestavit konkrétní opakovatelný zátěžový profil a jedním rozhraním spouštět lokální test i GitHub Actions.

- **Hold:** konstantní cílová intenzita po nastavenou dobu.
- **Bell:** nárůst intenzity → maximum → pokles.
- **Hold + Bell:** trvalá baseline a nad ní dočasná špička.
- **Recovery:** baseline → krátký spike → návrat na baseline. Jde o návrh zátěže, nikoli automatický důkaz obnovení systému po výpadku.
- Ovládací prvky převádějí zobrazení **RPM ↔ RPS**, mění fáze a okamžitě přepočítají SVG graf **očekávaného průběhu**, nikoli skutečně naměřené metriky.
- `Run` předá parametry lokálnímu Python runneru a spouští Locust **headless** proti lokálnímu FastAPI. Stav `Idle/Running/PASS/FAIL` se čte z lokálního podprocesu; `Stop` mu pošle SIGTERM.
- `Run GitHub` zavolá přes lokální backend UI `gh workflow run performance-locust.yml --ref main` a předá vybraný profil a parametry jako workflow inputs. Stav jobu dohledává pomocí GitHub API a request ID, zobrazuje odkaz na Actions a reporty.
- Validace parametrů omezuje nesmyslné nebo příliš rozsáhlé demo běhy; GitHub workflow má limit doby testu **300 sekund**.
- **Omezení:** mezi názvy `hold-bell` v UI a `hold_bell` v Python enumu existuje nesoulad; UI cesta profilu Hold + Bell proto vyžaduje opravu/ověření. Před pohovorem používejte **ověřený profil Hold**. Původní Locust dashboard ani Live GitHub metriky nejsou součástí vlastního UI.

### Schéma současného fungování

```text
                     POČÍTAČ / LOKÁLNÍ PROSTŘEDÍ
  http://127.0.0.1:8501  Moje vlastní konfigurační UI
           │
           ├─ Run ──────► Locust headless ──────► FastAPI:8000 ──► PostgreSQL
           │                       │                    │
           │                       └─ HTML/CSV           └─ OTLP → Dynatrace SaaS
           │
           └─ Run GitHub ─► GitHub Actions (dočasný runner)
                                  ├─ FastAPI + PostgreSQL
                                  ├─ Locust headless → reporty (Artifacts)
                                  └─ FastAPI → OTLP/HTTPS → Dynatrace SaaS
                                                atribut ci.github.run_id

  http://127.0.0.1:8089  Původní Locust Web UI (oddělený způsob lokálního běhu)
                                  └─ Locust → lokální FastAPI:8000
```

**Tři různá rozhraní:** vlastní UI na 8501 konfiguruje profily; původní Locust na 8089 sleduje lokálně běžící Locust; Dynatrace je vzdálená webová observabilita. Pro test `Run GitHub` nejsou lokální backend ani port 8089 potřeba.

## 4. Nejsnazší prezentace — UI + Run GitHub (bez Dockeru)

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

## 5. Dynatrace — důkaz konkrétního běhu

Otevřete [Distributed Tracing Explorer](https://oal44442.apps.dynatrace.com/ui/apps/dynatrace.distributedtracing/explorer?v=transactions) a nastavte časový rozsah pokrývající dokončený test.

- Vyhledejte service `secure-backend-platform`.
- Filtrujte resource atribut `ci.github.run_id` podle skutečného **RUN_ID**, například `44960706592`.
- Alternativně hledejte `deployment.environment.name = github-actions`.
- Otevřete requesty pro login, items a simulovanou platbu. HTTP 401/403 u negativních případů může být **očekávaný** výsledek.
- Rozlišujte tři věci: úspěšný CI běh, úspěšný Locust scénář a skutečně přijatý trace. Jedno **nedokazuje automaticky** druhé.

V referenčním běhu `44960706592` byl z Dynatrace Exploreru doložen filtr `ci.github.run_id` a **15 transakcí**. To není důkaz kompletního pokrytí všech negativních scénářů. Lokální FastAPI může emitovat trace se stejným `service.name`, ale bez tohoto GitHub run ID.

## 6. Volitelně — lokální FastAPI + PostgreSQL a tlačítko Run

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

## 7. Původní Locust Web UI (:8089) — samostatné lokální spuštění

Vyžaduje **běžící lokální backend a DB** podle kapitoly 6. V porovnání s vlastním UI (:8501) poskytuje originální Locust živé průběžné metriky a ovládání virtuálních uživatelů, ale nepoužívá naše čtyři custom profilové plánovače ani GitHub workflow. Nespouštějte zároveň další lokální zátěž, pokud chcete čistě měřit jeden test.

Z kořene repozitáře otevřete **nový terminál**:

```bash
cd ~/Programy/DevOps/secure-backend-platform
source .venv/bin/activate

uv run --locked python - <<'PY'
import os
from dotenv import dotenv_values

env = os.environ.copy()
env.update({
    key: value
    for key, value in dotenv_values(".env").items()
    if value is not None
})

os.execvpe(
    "uv",
    [
        "uv", "run", "--locked", "locust",
        "-f", "performance/locust/locustfile.py",
        "--host", "http://localhost:8000",
        "--web-host", "127.0.0.1",
        "--web-port", "8089",
    ],
    env,
)
PY
```

Otevřete **http://127.0.0.1:8089** a v Locust Web UI nastavte například **1 user**, **spawn rate 1 user/s** a host **http://localhost:8000**. Kliknutím **Start** spustíte lokální test, ve statistikách uvidíte skutečné počty požadavků, odezvy a chyby; ukončete tlačítkem **Stop** a pak **Ctrl+C** v terminálu.

**Proč předáváme `.env` přes Python?** `locustfile.py` při startu uživatele čte `FIRST_SUPERUSER` a `FIRST_SUPERUSER_PASSWORD` z prostředí. `uv run` samotné automaticky negarantuje načtení těchto hodnot. Použitý postup je načte bez výpisu do terminálu. Počty uživatelů a reálné RPS se nemusí rovnat cílovým RPM custom profilu.

## 8. Dynatrace — jak jej otevřít, zapnout export a ukázat

**Dynatrace v tomto PoC není lokální služba ani Docker kontejner.** Jde o cloudový tenant přístupný přes prohlížeč. Na počítači se spouští **instrumentovaný FastAPI backend**; ten odesílá trace do tenantu přes OTLP/HTTPS.

### Režim A: GitHub Actions + Dynatrace (doporučeno)

1. Přihlásit se do [Dynatrace Distributed Tracing Explorer](https://oal44442.apps.dynatrace.com/ui/apps/dynatrace.distributedtracing/explorer?v=transactions). Odkaz není veřejným přístupem bez příslušných oprávnění.
2. Zkontrolovat, že v GitHub repozitáři jsou **Actions Secrets** `DT_API_TOKEN` a `DT_OTLP_TRACES_ENDPOINT` (stačí jejich **existence**, nevypisujte obsah).
3. Spustit test pomocí `Run GitHub` v našem UI nebo záložním `gh workflow run`.
4. V logu jobu zkontrolovat krok `Start isolated backend` a zprávu `Dynatrace tracing: ENABLED`.
5. Ve webovém Dynatrace Exploreru nastavit rozsah času testu a filtrovat `ci.github.run_id = <RUN_ID>`, případně `deployment.environment.name = github-actions`.

```bash
gh secret list --repo Necraatall/secure-backend-platform
```

### Režim B: lokální Docker FastAPI + Dynatrace

V soukromém lokálním `.env` (nikoli v Gitu) musí být konfigurováno:

```dotenv
DT_TRACING_ENABLED=true
DT_OTLP_TRACES_ENDPOINT=<HTTPS_OTLP_TRACES_URL>
DT_API_TOKEN=<SECRET_TOKEN>
```

Hodnoty **nikdy neposílejte na obrazovku při pohovoru**. Po změně `.env` je potřeba backend kontejner znovu vytvořit, aby převzal nové prostředí:

```bash
docker compose up -d --force-recreate backend
```

Ověření pouze **přítomnosti** proměnných bez zobrazení hodnot:

```bash
docker compose exec -T backend python - <<'PY'
import os
for name in ("DT_TRACING_ENABLED", "DT_OTLP_TRACES_ENDPOINT", "DT_API_TOKEN"):
    print(f"{name}: {'CONFIGURED' if os.getenv(name) else 'MISSING'}")
PY
```

Potom odešlete několik autorizovaných požadavků pomocí lokálního Locustu nebo pro základní test endpointu:

```bash
curl -i http://127.0.0.1:8000/api/v1/items/
```

Zde je **HTTP 401 očekávané**, protože není přiložen přístupový token; přesto může vzniknout trace. V Dynatrace zkontrolujte service `secure-backend-platform`, cestu `/api/v1/items/` a správný časový interval. **Lokální běh obvykle nemá atribut `ci.github.run_id`**.

**Pokud chcete jen ukázat existující prokázaný výsledek**, otevřete historický GitHub běh [44960706592](https://github.com/Necraatall/secure-backend-platform/actions/runs/44960706592) a v Dynatrace vyhledejte stejné run ID ve správném historickém čase; aktuální dashboard se může lišit podle retence dat.

## 9. Ukončení

- UI server v terminálu A: **Ctrl+C**.
- Lokální Locust běh: tlačítko **Stop** v UI, nebo vyčkat na dobu testu.
- Lokální Docker kontejnery (jen pokud jste je spouštěli v kroku 6):

```bash
docker compose down
docker compose ps
```

`docker compose down` bez `-v` neodstraňuje pojmenované databázové volumes. **Nezastavuje Docker službu jako celek.** GitHub Actions job naopak po dokončení sám provádí `docker compose down -v --remove-orphans` ve vlastním izolovaném runneru. Trvale připravená cloudová testovací instance v současném PoC **neexistuje**.

## 10. Diagnostika

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

## 11. Krátký scénář pro pohovor (cca 5 minut)

1. Otevřít konfigurační UI a vysvětlit čtyři **návrhy profilů zátěže**.
2. Nastavit Hold 30 RPM / 20 s a ukázat graf plánovaného průběhu.
3. Spustit `Run GitHub`, případně fallback přes `gh workflow run`.
4. Na GitHubu ukázat startup backendu, healthcheck, Locust, artifacts a cleanup.
5. V Dynatrace filtrovat skutečné `ci.github.run_id` a ukázat trasování login/items/payment.
6. V [ADR](LOCUST_DYNATRACE_POC.md) vysvětlit, proč zatím používáme dočasný runner místo stále běžící infrastruktury.

**Scope:** PoC je předveditelný, ale není to produkční platforma, public remote dashboard, výkonnostní garance ani doklad úplné funkční coverage API scénářů.
