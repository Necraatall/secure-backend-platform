# Locust + Dynatrace PoC — stav, omezení a odložené práce

Datum záznamu: **2026-11-21**. Projekt **Secure Backend Platform** je širší aplikace/platforma (FastAPI, PostgreSQL, frontend, CI/CD, DevSecOps); **jen Locust + Dynatrace integrace je PoC**.

## Co je implementováno / ověřeno
- GitHub Actions manuální workflow `.github/workflows/performance-locust.yml`: volba profilu `hold`, `bell`, `hold-bell`, `recovery`, RPM, fáze a tolerance; izolovaný Docker Compose backend + PostgreSQL, healthcheck, databázová inicializace, ověření přihlášení, headless Locust, upload HTML/CSV reportů a cleanup.
- Každý ze čtyř profilů už měl úspěšný samostatný GitHub Actions běh: Hold [44931259685](https://github.com/Necraatall/secure-backend-platform/actions/runs/44931259685), Bell [44932559678](https://github.com/Necraatall/secure-backend-platform/actions/runs/44932559678), Hold + Bell [44934589171](https://github.com/Necraatall/secure-backend-platform/actions/runs/44934589171), Recovery [44932564772](https://github.com/Necraatall/secure-backend-platform/actions/runs/44932564772). Jde o ověření příslušných běhů, **ne o automaticky prokázané pokrytí všech API scénářů v každém běhu**.
- Lokální konfigurační UI `performance/locust/ui.py` (port 8501) umožňuje nastavit profil/parametry, ukazuje cílovou křivku; uživatelsky ověřeno odeslání GitHub workflow a zobrazení stavu `success`. **Pozor: v době záznamu není `ui.py` součástí `main`, ale je lokálně necommitovaný; tato dokumentace nepotvrzuje jeho dostupnost při čistém klonu.**
- Lokální originální Locust Web UI používá port 8089. Není to dashboard GitHub-hosted testu.
- FastAPI má volitelnou OpenTelemetry instrumentaci v `backend/app/core/telemetry.py`, zapínanou `DT_TRACING_ENABLED=true`, s `DT_OTLP_TRACES_ENDPOINT` a `DT_API_TOKEN` mimo Git. Instrumentaci volá `backend/app/main.py`.
- Zátěžové testy jsou určeny pro **autorizované izolované prostředí a syntetická data**; workflow není veřejně dostupným cílem pro zátěž.

## Co nebylo prokázáno / není dokončeno
- **Dynatrace end-to-end: NOT VERIFIED.** Samotná existence exporteru neprokazuje doručení spanů, správné mapování service, časové období ani funkční dashboard. Je nutné doložit skutečné trace přijaté tenantem při lokálním testu, bez zveřejnění tokenů. GitHub Actions workflow aktuálně nastavuje `.env` z `.env.example`, takže z něj nelze tvrdit export do Dynatrace.
- **API coverage při krátkém Locust testu není garantováno**: tasky se vybírají váženě/náhodně. Pro úplné integrační ověření je nutný důkaz ze statistik pro přihlášení, načtení items, úspěšnou platbu, zamítnutou platbu a neplatný token.
- **Live Locust Web UI pro Run GitHub není součást současného PoC.** GitHub-hosted runner je dočasný, spouští `--headless`, jeho port 8089 není veřejně přístupný. Screenshot lokálního Web UI není důkaz vzdáleného živého dashboardu.
- Lokální konfigurační UI zatím neposkytuje živé vzdálené metriky Locustu a grafy naměřené z GitHub běhu v jednom panelu; odkazuje na GitHub Actions a následné reporty.
- Zprovoznění celé aplikace ve vzdáleném cloudu ani trvalé testovací prostředí nejsou částí tohoto PoC.

## TODO — odloženo do cloudového nasazení
Sledovat v [Issue #22](https://github.com/Necraatall/secure-backend-platform/issues/22), spolu s architekturou/TCO/IaC v [Issue #21](https://github.com/Necraatall/secure-backend-platform/issues/21):
- [ ] Při nasazení aplikace do vzdáleného prostředí nasadit i samostatně ovládaný Locust.
- [ ] Zabezpečené HTTPS, autentizace/autorizace a živý dashboard odpovídající aktuálně spuštěnému testu.
- [ ] Z UI spouštět **pouze vybraný** profil s nastavenými parametry, přejít na jeho živé metriky a ovládat Stop.
- [ ] Ruční Start environment → opakované testy → Stop environment, bez povinného scheduleru.
- [ ] Ukládat reporty nezávisle na životnosti prostředí; propojit Locust run, GitHub run a Dynatrace trace.
- [ ] Srovnat náklady AWS, GCP a levnějších/free variant, provozní limity a bezpečnost; infrastrukturu navrhnout jako IaC bez předem vynuceného frameworku.
- [ ] Doložit skutečné end-to-end ověření po nasazení.

**Rozhodnutí 2026-11-21:** GitHub Actions ponechat v současném headless režimu. Ve stávajícím PoC nebudovat veřejný tunel ani nový vzdálený Locust dashboard. Nezaměňovat tento odklad za dokončené Dynatrace ověření.

## Pro úplné uzavření současného PoC
- [ ] Prokázat přijetí spanů v Dynatrace (timestamp, service, relevantní endpointy; bez tokenů).
- [ ] Doložit reprezentativní Locust report a reálné pokrytí zamýšlených API operací.
- [ ] Commitnout a ověřit lokální `ui.py`, je-li součástí předávaného PoC, včetně základních testů a korektních stavů PASS/FAIL.
- [ ] Ověřit čistý checkout a aktualizovat výsledek v Issue #20 včetně SHA.
