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
- **Dynatrace lokálně: VERIFIED (uživatelský screenshot 2026-11-21).** Distributed Tracing ukazuje `secure-backend-platform`, `GET /api/v1/items/` s HTTP 401 a healthcheck s HTTP 200; jde o reálně přijaté trace. **GitHub → Dynatrace: funkčně pozorováno, původ konkrétních trace ještě není strojově jednoznačně korelován.** Workflow od commitu `3a0d9df` předává `DT_API_TOKEN` a `DT_OTLP_TRACES_ENDPOINT` z GitHub Secrets a zapíná tracing při startu izolovaného backendu. Uživatel ohlásil `success` GitHub testu; ve stejném období viděl v Dynatrace login, items a payments. Pro průkaznou atribuci přidat `github.run_id`/identifikátor testu jako resource/span atribut a ověřit jej přímo v trasách. Samotné `success` nedokazuje ingest Dynatrace.
- **API coverage při krátkém Locust testu není garantováno**: tasky se vybírají váženě/náhodně. Pro úplné integrační ověření je nutný důkaz ze statistik pro přihlášení, načtení items, úspěšnou platbu, zamítnutou platbu a neplatný token.
- **Live Locust Web UI pro Run GitHub není součást současného PoC.** GitHub-hosted runner je dočasný, spouští `--headless`, jeho port 8089 není veřejně přístupný. Screenshot lokálního Web UI není důkaz vzdáleného živého dashboardu.
- Lokální konfigurační UI zatím neposkytuje živé vzdálené metriky Locustu a grafy naměřené z GitHub běhu v jednom panelu; odkazuje na GitHub Actions a následné reporty.
- Zprovoznění celé aplikace ve vzdáleném cloudu ani trvalé testovací prostředí nejsou částí tohoto PoC.


## Architektura, životní cyklus a zdůvodnění rozhodnutí

### Současný režim — jeden izolovaný běh na jeden test

~~~text
Lokální konfigurační UI (:8501)
       │ Run GitHub (zvolený profil + parametry)
       ▼
GitHub Actions (nový dočasný runner / nový job)
       │
       ├─ checkout + uv sync
       ├─ .env.example → .env; Dynatrace z GitHub Secrets
       ├─ docker compose up: PostgreSQL + FastAPI
       ├─ úvodní čekání na health-check (max. 60 pokusů po 3 s)
       ├─ inicializace DB a ověření přihlášení
       ├─ Locust headless: HOLD / BELL / HOLD-BELL / RECOVERY
       │       ├── HTML/CSV → GitHub Actions artifacts
       │       └── HTTP → FastAPI → OTLP/HTTPS → Dynatrace
       └─ docker compose down -v --remove-orphans (always)
                └─ runner po jobu končí
~~~

**Důsledek:** každé spuštění opakuje přípravu a izolovaná instance po testu neběží. Úspěšná pipeline **není** čekající stroj, který lze z UI znovu použít. GitHub-hosted runner nelze tímto workflow ponechat jako trvalý interaktivní server.

### Cílový režim — až s řízeným cloudovým prostředím (Issue #22)

~~~text
Konfigurační UI
    │
    ├─ Start prostředí ──► řízená instance: FastAPI + PostgreSQL
    │                               │
    │                               └─ OTLP/HTTPS → Dynatrace
    ├─ Run Hold ──────────┐
    ├─ Run Bell ──────────┼──► opakované nezávislé Locust běhy
    ├─ Run Recovery ──────┘         │
    │                               └─ reporty mimo životnost instance
    └─ Stop prostředí ───► uvolnění cloudových zdrojů
~~~

**To je návrh, nikoli nasazená funkcionalita.** Bude nutné vyřešit autentizované ovládání životního cyklu, ochranu testovacího cíle, automatické ukončení při nečinnosti nebo chybě, náklady a limity free tieru, data/izolaci jednotlivých běhů a per-run korelaci telemetrie.

### Healthcheck není čekající pipeline

| Mechanismus | Účel | Frekvence a životnost |
| --- | --- | --- |
| GitHub krok \`Wait for health-check\` | Po startu ověří připravenost backendu před inicializací/testem | Opakuje po 3 s, nejvýše 60 pokusů; po úspěchu končí |
| Docker Compose \`backend.healthcheck\` | Průběžná kontrola stavu **běžícího kontejneru** | V \`compose.yml\` interval 10 s, až do zastavení kontejneru |
| Dynatrace tracing | Diagnostika výkonu a požadavků aplikace | Zachycuje instrumentované requesty včetně healthchecků, nejsou-li filtrovány |

Každých 10 s znamená přibližně **6 požadavků/min, 360/h, 8 640/den** na jeden nepřetržitě běžící kontejner. U jednoduchého endpointu bývá aplikační zátěž malá, ale množství trace zvyšuje šum a může spotřebovávat ingestní kvótu. Healthcheck běží i **lokálně**, není důkazem trvale spuštěné GitHub pipeline. Po úspěšném GitHub jobu je předepsán \`docker compose down -v --remove-orphans\`; lokální Docker kontejnery jsou nezávislé. Změna intervalu na 60 s či vyloučení healthchecků z OTLP je **návrh, nikoli provedená změna**. Nepovažovat samotné healthchecky za výkonnostní Locust zátěž.

### Rozhodnutí pro technický pohovor (Architecture Decision Record)

| Rozhodnutí | Proč nyní | Alternativa / nevýhoda | Kdy přehodnotit |
| --- | --- | --- | --- |
| Izolovaný GitHub runner pro každý test | Reprodukovatelnost, čistá DB a snadný cleanup; nepotřebuje placenou trvalou infrastrukturu | Opakovaný build, start a init DB prodlužují testovací cyklus | Až časté interaktivní testy ospravedlní persistentní prostředí |
| Manuální volba jednoho profilu | Operátor kontroluje RPM, délku, cíl a spotřebu; jednotlivé scénáře lze vyhodnotit samostatně | Není to automatická čtyřprofilová regresní sada | Při zavedení pravidelných benchmarků |
| Headless Locust + artifacts | GH runner nemá stálý veřejný endpoint; výsledky HTML/CSV přežijí konec jobu | Není živý vzdálený Locust Web UI ani okamžité Stop z našeho UI | Cloudové nasazení, Issue #22 |
| Přímý OpenTelemetry OTLP/HTTPS export z FastAPI | Minimální PoC infrastruktura; existující instrumentace, bez instalace OneAgentu | Menší šíře infrastrukturové telemetrie; potřeba zajistit secrets a korelaci | Širší observabilita nebo více služeb |
| Dynatrace token výhradně v GitHub Secrets | Necommitovat přihlašovací údaje; předat je jen při startu backendu | Nutnost správy a rotace tokenu; secrets nedostupné pro některé typy fork PR | Při vývoji bezpečnějšího identity modelu |
| Stop/cleanup po testu | Omezit náklady, nezanechávat testovací služby a data | Prostředí nelze opakovaně využívat mezi joby | Při zavedení Start/Run/Stop s TTL a rozpočtovým limitem |
| Ponechat Docker healthcheck odděleně od startup checku | Jednorázová *readiness* a průběžná *health* řeší odlišné otázky | Duplicitní volání, šum v trace při 10s intervalu | Upravit interval / trace filtering po měření provozu |

**Jak rozhodnutí obhájit:** Nejprve prokázat opakovatelné E2E zátěžové běhy, ukládat artefakty a měřit skutečný backend v Dynatrace. Teprve potom investovat do trvale běžícího testovacího prostředí. Kritéria úspěchu jsou oddělená: \`GitHub success\` = testovací workflow prošlo; \`Dynatrace trace\` = dorazila telemetrie; \`run_id\` ve spanu = dohledatelný původ konkrétního testu. Tyto důkazy se nesmějí zaměňovat.

### Rizika a provozní důsledky

- **Náklady:** nový runner a opakovaný build znamenají čas CI; trvalá instance by naopak mohla vytvářet cloudové náklady mimo testy.
- **Zkreslení metrik:** zahrnutí zdravotních kontrol do grafů requestů uměle zvýší objem provozu; testovací RPS/RPM se vyhodnocují primárně z Locust reportu.
- **Bezpečnost:** token držet v Secrets, nikoli v artefaktech; v budoucí cloudové instanci vyžadovat přístupová pravidla a limit zátěže.
- **Identifikace běhu:** stejný \`service.name=secure-backend-platform\` pro lokální i GitHub backend znamená, že samotný seznam transakcí nerozlišuje zdroj. Potřebujeme \`run_id\` a prostředí jako atributy trace.
- **Úklid:** \`if: always()\` není absolutní garance při selhání runneru; u persistentního prostředí navíc TTL/failsafe ukončení.

## TODO — odloženo do cloudového nasazení
Sledovat v [Issue #22](https://github.com/Necraatall/secure-backend-platform/issues/22), spolu s architekturou/TCO/IaC v [Issue #21](https://github.com/Necraatall/secure-backend-platform/issues/21):
- [ ] Při nasazení aplikace do vzdáleného prostředí nasadit i samostatně ovládaný Locust.
- [ ] Zabezpečené HTTPS, autentizace/autorizace a živý dashboard odpovídající aktuálně spuštěnému testu.
- [ ] Z UI spouštět **pouze vybraný** profil s nastavenými parametry, přejít na jeho živé metriky a ovládat Stop.
- [ ] Ruční Start environment → opakované testy → Stop environment, bez povinného scheduleru.
- [ ] Ukládat reporty nezávisle na životnosti prostředí; propojit Locust run, GitHub run a Dynatrace trace.
- [ ] Srovnat náklady AWS, GCP a levnějších/free variant, provozní limity a bezpečnost; infrastrukturu navrhnout jako IaC bez předem vynuceného frameworku.
- [ ] Doložit skutečné end-to-end ověření po nasazení.

**Rozhodnutí 2026-11-21:** GitHub Actions ponechat v současném headless režimu. Ve stávajícím PoC nebudovat veřejný tunel ani nový vzdálený Locust dashboard. Dynatrace ingest byl následně lokálně ověřen; přesnou atribuci vzdálených trace k run ID ještě doplnit.

## Pro úplné uzavření současného PoC
- [x] Prokázat lokální přijetí spanů v Dynatrace (uživatelský screenshot: service, čas a endpointy; bez tokenů).
- [ ] Doplnit jednoznačnou korelaci GitHub run ID s Dynatrace trace a archivovat důkaz.
- [ ] Doložit reprezentativní Locust report a reálné pokrytí zamýšlených API operací.
- [ ] Commitnout a ověřit lokální `ui.py`, je-li součástí předávaného PoC, včetně základních testů a korektních stavů PASS/FAIL.
- [ ] Ověřit čistý checkout a aktualizovat výsledek v Issue #20 včetně SHA.
