# Gestione Lavoro Agile

Applicazione on-premise per pianificazione e approvazione del lavoro agile. Versione 2.0.0.

Backend Django per gestione mensile del calendario di lavoro agile con autenticazione LDAP o locale, workflow di approvazione e audit log.

## Funzionalita incluse

- Login con token (`/api/auth/login/`) usando backend locale o LDAP
- Gestione utenti con ruoli: `EMPLOYEE`, `ADMIN`, `SUPERADMIN`
- Piano mensile per dipendente (`MonthlyPlan`) con dettaglio giornaliero (`PlanDay`)
- Workflow: `DRAFT -> SUBMITTED -> APPROVED/REJECTED`
- Revisione da parte degli amministratori
- Tracciamento eventi principali in `AuditLog`
- Pannello amministrativo Django (`/admin/`)
- Portale web unico con area dipendente e coda approvazioni per `ADMIN`/`SUPERADMIN`
- Scheda utente nel portale con `Nome e cognome`, `Afferenza territoriale` e `Responsabile approvazione`
- Gli approvatori possono aprire il dettaglio giornaliero del piano prima di approvare/rifiutare
- Invio email automatico al dipendente quando il piano viene approvato o rifiutato
- I dipendenti possono modificare il piano del mese corrente e del mese successivo; il mese corrente non e inviabile in approvazione ma solo in richiesta variazione

## Stack

- Python 3.12
- Django 5 + Django REST Framework
- PostgreSQL 16
- LDAP opzionale con `django-auth-ldap`

## Perché Django

Django offre un livello di sicurezza superiore out-of-the-box, grazie a protezioni integrate contro SQL injection, XSS e CSRF. Questo lo rende particolarmente adatto a un'applicazione gestionale con autenticazione, ruoli, workflow approvativi e interfaccia amministrativa. La precedente versione sviluppata con Node.js era piu flessibile, ma richiedeva maggiore attenzione su configurazioni di sicurezza, dipendenze e codice custom nelle aree piu sensibili.

## Avvio rapido (Docker)

1. Copia variabili ambiente:

```bash
cp .env.example .env
```

2. Imposta almeno queste variabili in `.env`:

```env
DJANGO_SECRET_KEY=una-chiave-forte
DEBUG=1
AGILE_SITES=Sede principale
AGILE_DATE_DISPLAY_FORMAT=IT
AGILE_LOGIN_LOGO_URL=https://example.org/static/logo-istituto.png
POSTGRES_DB=agile_work
POSTGRES_USER=agile
POSTGRES_PASSWORD=agile
POSTGRES_HOST=db
POSTGRES_PORT=5432
LDAP_ENABLED=0
```

Riepilogo rapido variabili ambiente:
- obbligatorie minime: `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`
- quasi sempre da impostare: `ALLOWED_HOSTS`, `DEBUG`, `TIME_ZONE`
- identita applicazione: `AGILE_COMPANY_NAME`, `AGILE_COPYRIGHT_YEAR`, `AGILE_LOGIN_LOGO_URL`, `AGILE_FAVICON_URL`
- portale e sedi: `AGILE_DATE_DISPLAY_FORMAT`, `AGILE_SITES`
- database: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`
- LDAP: `LDAP_ENABLED`, `LDAP_SERVER_URI`, `LDAP_BIND_DN`, `LDAP_BIND_PASSWORD`, `LDAP_USER_BASE_DN`, `LDAP_USER_FILTER`
- email: `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `EMAIL_USE_SSL`, `DEFAULT_FROM_EMAIL`, `AGILE_EMAIL_FROM_NAME`, `AGILE_EMAIL_REDIRECT_TO`
- log e monitor admin: `AGILE_LOG_FILE`, `AGILE_LOG_LEVEL`, `AGILE_LOG_MONITOR_FILE`, `AGILE_LOG_MONITOR_SOURCES`, `AGILE_LOG_MONITOR_REFRESH_SECONDS`
- scheduler: `REMINDER_CHECK_INTERVAL_SECONDS`
- bootstrap superuser Docker: `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, `DJANGO_SUPERUSER_PASSWORD`

Note rapide:
- `ALLOWED_HOSTS`: in sviluppo tipico `localhost,127.0.0.1`; in produzione inserire domini/IP reali esposti
- `AGILE_DATE_DISPLAY_FORMAT`: `IT` per `gg/mm/aaaa`, `ISO` per `aaaa-mm-gg`
- `AGILE_SITES`: elenco separato da virgole delle afferenze territoriali disponibili (eventuali sedi secondarie)
- `AGILE_LOGIN_LOGO_URL` e `AGILE_FAVICON_URL`: URL assoluti opzionali per logo login e favicon
- `AGILE_EMAIL_REDIRECT_TO`: utile in sviluppo/test per reindirizzare tutte le email a una casella di sicurezza

Per il dettaglio completo di tutte le variabili supportate: [`docs/variabili_env.md`](docs/variabili_env.md)

3. Avvia:

```bash
docker compose up --build
```

4. App disponibile su:
- Portale dipendenti: `http://localhost:8001/`
- API: `http://localhost:8001/api/`
- Admin: `http://localhost:8001/admin/`

### Installazione automatica da zero (Linux)

E disponibile uno script installer idempotente che:
- verifica/installa Docker + Docker Compose (apt/dnf)
- crea directory di installazione
- clona/aggiorna il repository
- prepara `.env` da `.env.example`
- avvia lo stack Docker

Esempio:

```bash
bash scripts/install.sh \
  --install-dir /opt/lagile-management \
  --repo-url https://github.com/maxtoor/lagile.management.git \
  --branch main \
  --port 8001

# Solo simulazione (nessuna modifica)
bash scripts/install.sh --dry-run
```

Esecuzione diretta da GitHub (senza clone manuale):

```bash
curl -fsSL https://raw.githubusercontent.com/maxtoor/lagile.management/main/scripts/install.sh | bash -s -- \
  --install-dir /opt/lagile-management \
  --repo-url https://github.com/maxtoor/lagile.management.git
```

Alternativa con `wget`:

```bash
wget -qO- https://raw.githubusercontent.com/maxtoor/lagile.management/main/scripts/install.sh | bash -s -- \
  --install-dir /opt/lagile-management \
  --repo-url https://github.com/maxtoor/lagile.management.git
```

Opzioni principali:
- `--app-user <utente>` proprietario file installazione
- `--skip-docker-install` se Docker e gia presente
- `--dry-run` mostra i comandi senza eseguirli
- `--help` elenco completo opzioni

Comandi rapidi da server nuovo:

```bash
git clone https://github.com/maxtoor/lagile.management.git
cd lagile.management

# Simulazione (consigliata prima esecuzione)
bash scripts/install.sh --dry-run --install-dir /opt/lagile-management --branch main --port 8001

# Installazione reale
bash scripts/install.sh --install-dir /opt/lagile-management --branch main --port 8001
```

### Upgrade applicazione (Linux, Docker)

E disponibile uno script di aggiornamento con backup pre-upgrade:
- backup DB PostgreSQL + copia `.env`
- aggiornamento codice (`git pull --ff-only`)
- rebuild container `web`/`scheduler`
- migrate + check post-upgrade

Esempi:

```bash
# Simulazione (consigliata)
bash scripts/upgrade.sh --dry-run

# Upgrade reale
bash scripts/upgrade.sh
```

Opzioni utili:
- `--project-dir /opt/lagile-management` se il progetto non e nella directory corrente
- `--branch main` branch remoto da usare
- `--skip-backup` se vuoi saltare il backup
- `--skip-fetch` se hai gia fatto fetch/pull manuale
- `--skip-migrate` se vuoi eseguire migrate separatamente
- `--allow-dirty` per forzare anche con working tree non pulita

Nota Docker:
- e presente un servizio `scheduler` che esegue periodicamente:
  - `send_submission_reminders` (promemoria utente ultimo giorno mese)
  - `send_manager_monthly_summary` (riepilogo referente primo giorno mese)
  - `prepare_next_year_holidays` (il 1 dicembre prepara le festivita dell'anno successivo e invia report ai superuser)
- intervallo controllo configurabile con `REMINDER_CHECK_INTERVAL_SECONDS` (default `86400`)
- i comandi inviano realmente email solo nel loro giorno previsto (a meno di `--force`)
- nella Pagina di Amministrazione e disponibile il link `Monitor log` per visualizzare il tail live e selezionare la sorgente (es. `app` / `scheduler`)

## Avvio locale (senza Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
export $(grep -v '^#' .env | xargs)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Riferimento rapido configurazione:
- dettagli di tutte le variabili `.env`: [`docs/variabili_env.md`](docs/variabili_env.md)

Override da interfaccia Pagina di Amministrazione:
- in `Strumenti` e disponibile `Impostazioni applicazione`
- i valori salvati in questa pagina hanno priorita su `.env` per:
  - formato data portale
  - logo login
  - nome azienda + anno copyright
  - mittente email (`DEFAULT_FROM_EMAIL`, `AGILE_EMAIL_FROM_NAME`)

## Deploy con Portainer (Docker Compose)

Questa procedura usa direttamente `docker-compose.yml` e file `.env`, senza modifiche lato host oltre a Docker/Portainer.

Prerequisiti:
- Portainer attivo e raggiungibile
- Docker engine sul nodo target
- sorgenti del progetto disponibili sul nodo (git clone oppure upload stack)
- porte libere (default `8001` per `web`)

Passi:
1. In Portainer, apri `Stacks` -> `Add stack`.
2. Scegli `Web editor` (incolla il contenuto di `docker-compose.yml`) oppure `Repository` (se vuoi puntare al repo git).
3. Configura le variabili ambiente:
   - opzione consigliata: usa il file `.env` del progetto sul nodo
   - in alternativa, imposta in Portainer le variabili equivalenti (`POSTGRES_*`, `LDAP_*`, `EMAIL_*`, `TIME_ZONE`, ecc.).
4. Deploy dello stack.
5. Verifica che i container siano `running`:
   - `web`
   - `db`
   - `scheduler`

Post-deploy (una tantum):
1. Esegui migrazioni:
   - `python manage.py migrate` (container `web`)
2. Crea il superuser Django:
   - `python manage.py createsuperuser`
3. Verifica accesso:
   - Portale: `http://<host>:8001/`
   - Admin: `http://<host>:8001/admin/`

Operativita:
- Restart servizi: da Portainer (`Stacks` -> stack -> `Restart`)
- Log: usa la sezione log del container (`web`/`scheduler`/`db`)
- Aggiornamento applicazione:
  1. aggiorna sorgenti/branch
  2. `Re-deploy` dello stack con rebuild se necessario

Persistenza e backup:
- Il database PostgreSQL usa il volume Docker `pg_data`.
- Effettua backup periodico del DB (dump SQL) e conserva anche `.env`.

Troubleshooting rapido:
- `port is already allocated`: cambia mapping porta in `docker-compose.yml` (es. `8002:8000`) e redeploy.
- `.env not found`: crea/copia `.env` accanto a `docker-compose.yml`.
- LDAP non raggiungibile: verifica `LDAP_SERVER_URI`, rete e firewall dal nodo Docker.
- Email non inviate: verifica `EMAIL_HOST`, `EMAIL_PORT`, credenziali SMTP e log `web`.

## Endpoints principali

- `POST /api/auth/login/`
  - body: `{ "username": "...", "password": "..." }`
  - response: token + profilo
- `GET /api/auth/me/`
  - include anche `manager_id`, `manager_name`, `aila_subscribed`, `auto_approve`
- `GET/POST /api/plans/`
- `GET/PUT/PATCH /api/plans/{id}/`
- `POST /api/plans/{id}/submit/` (dipendente)
- `POST /api/plans/{id}/request_change/` (dipendente, solo mese corrente)
- `POST /api/plans/{id}/review/` (admin)
- `GET /api/holidays/month/?year=YYYY&month=MM`
  - body approvazione: `{ "approve": true }`
  - body rifiuto: `{ "approve": false, "reason": "..." }`

Header auth richiesto:

```text
Authorization: Token <token>
```

Esempio risposta profilo utente:

```json
{
  "id": 12,
  "username": "mrossi",
  "email": "mrossi@example.org",
  "first_name": "Mario",
  "last_name": "Rossi",
  "department": "Napoli",
  "manager_id": 4,
  "manager_name": "Luigi Bianchi",
  "role": "EMPLOYEE",
  "aila_subscribed": false,
  "is_staff": false,
  "is_superuser": false
}
```

## LDAP

Abilita LDAP con:

```env
LDAP_ENABLED=1
LDAP_SERVER_URI=ldap://ldap.example.org:389
LDAP_BIND_DN=cn=svc_ldap,ou=svc,dc=example,dc=org
LDAP_BIND_PASSWORD=...
LDAP_USER_BASE_DN=ou=people,dc=example,dc=org
LDAP_USER_FILTER=(uid=%(user)s)
LDAP_ATTR_DEPARTMENT=ou
LDAP_IMPORT_FILTER=(objectClass=person)
```

Con `LDAP_ENABLED=0` resta attivo il login locale Django.

### Import utenti LDAP in locale (non attivi)

Per importare utenti LDAP nel DB locale e gestirli manualmente:

```bash
python manage.py import_ldap_users
```

Opzioni utili:

```bash
python manage.py import_ldap_users --dry-run
python manage.py import_ldap_users --base-dn "ou=people,dc=example,dc=org" --filter "(objectClass=person)"
```

Note:
- gli utenti importati (nuovi o aggiornati) vengono impostati `is_active=False`
- agli utenti importati viene impostata password locale non utilizzabile
- il campo `Afferenza territoriale` viene valorizzato solo se il valore LDAP e tra quelli ammessi da `AGILE_SITES`, altrimenti resta vuoto

### Sync periodico utenti LDAP (allineamento)

Per allineare gli utenti gia importati quando LDAP cambia:

```bash
python manage.py sync_ldap_users --dry-run
python manage.py sync_ldap_users
python manage.py sync_ldap_users --deactivate-missing
python manage.py sync_ldap_users --create-missing
```

Regole sync:
- chiave di allineamento: `username`
- campi aggiornati dal sync: `first_name`, `last_name`, `email`
- campi non toccati: `Afferenza territoriale`, `Responsabile approvazione`, `Sottoscrizione AILA`, `Ruolo`, `Auto-approvazione`
- gli account locali con password utilizzabile non vengono modificati
- per default non crea utenti mancanti (evita import massivo involontario)
- con `--create-missing` crea in locale gli utenti LDAP assenti nel DB
- con `--deactivate-missing` vengono disattivati gli account LDAP locali non piu presenti su LDAP (solo account con password non utilizzabile)

## Import/Export release (JSON)

Per trasferire configurazione e anagrafica base tra installazioni (es. bootstrap nuova istanza) sono disponibili:

```bash
python manage.py export_release_data ./release-export.json
python manage.py import_release_data ./release-export.json --dry-run
python manage.py import_release_data ./release-export.json --mode merge
python manage.py import_release_data ./release-export.json --mode replace
```

Contenuti esportati:
- utenti (anagrafica applicativa, ruolo, referente, gruppi, stato AILA/auto-approvazione)
- gruppi
- policy afferenze territoriali (`DepartmentPolicy`)
- festivita (`Holiday`)
- template email di sistema
- impostazioni applicazione (`AppSetting`)

Note operative:
- formato versionato: `schema_version=1`
- `--dry-run` valida e simula senza salvare modifiche
- `--mode merge` (default): upsert senza cancellazioni
- `--mode replace`: oltre all'upsert, sostituisce dataset di `DepartmentPolicy`, `Holiday`, `SystemEmailTemplate` e `AppSetting` (non cancella utenti)
- gli utenti nuovi vengono creati con password locale non utilizzabile
- il campo referente viene assegnato in seconda fase usando `manager_username`

Flusso consigliato installazione ex-novo:
1. deploy stack + migrate + superuser
2. `import_release_data` dal file export della sorgente
3. verifica accesso admin/portale e test SMTP
4. eventuale import CSV ICB dalla pagina `Strumenti`

## Migrazione dalla versione precedente

Nota: questa procedura riguarda esclusivamente gli Istituti del CNR che avevano adottato la versione precedente di questo software.

Dettagli operativi nel documento dedicato:
- [`docs/migrazione_cnr.md`](docs/migrazione_cnr.md)

## Email notifiche

Configura SMTP in `.env`:

```env
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.org
EMAIL_PORT=587
EMAIL_HOST_USER=mailer@example.org
EMAIL_HOST_PASSWORD=...
EMAIL_USE_TLS=1
EMAIL_USE_SSL=0
DEFAULT_FROM_EMAIL=noreply@example.org
AGILE_EMAIL_FROM_NAME=Lagile.management
AGILE_EMAIL_REDIRECT_TO=dev-mailbox@example.org
```

Nota: in assenza di configurazione SMTP resta il backend console (`EMAIL_BACKEND` di default), utile in sviluppo.
Se `AGILE_EMAIL_FROM_NAME` e valorizzato, il mittente viene inviato nel formato `Nome <indirizzo>`.
Se `AGILE_EMAIL_REDIRECT_TO` e valorizzato, tutte le email in uscita vengono inviate solo a quella casella invece che ai destinatari reali: utile per sviluppo e collaudo.

Template email modificabili dalla Pagina di Amministrazione:
- sezione: `Template email di sistema`
- chiavi disponibili:
  - `CHANGE_REQUEST_SUBMITTED`
  - `REMINDER_PENDING_SUBMISSION`
  - `MANAGER_MONTHLY_SUMMARY`
  - `PLAN_APPROVED`
  - `PLAN_REJECTED`
  - `CHANGE_APPROVED`
  - `CHANGE_REJECTED`
- segnaposto utili nei template:
  - `{first_name_or_username}`, `{first_name}`, `{last_name}`, `{full_name}`, `{username}`
  - `{manager_name}`, `{employee_name}`
  - `{pending_count}`, `{missing_count}`, `{pending_lines}`, `{missing_lines}`
  - `{month_label}`, `{month_name_year}`, `{status_label}`, `{status_label_lower}`
  - `{plan_status}`, `{plan_status_label}`
  - `{change_reason}`, `{rejection_reason}`, `{final_line}`
- dalla scheda template e disponibile il pulsante `Invia email di test` con anteprima e invio verso destinatario scelto
- eventi email principali:
  - invio richiesta variazione: email al referente amministrativo dell'utente
  - ultimo giorno del mese: promemoria invio piano al mese successivo per utenti attivi senza auto-approvazione che non hanno ancora stato `SUBMITTED`/`APPROVED` (una sola volta per utente/mese target)
  - primo giorno del mese: email riepilogo al referente con piani in attesa di approvazione e utenti assegnati senza piano del mese corrente (una sola volta per referente/mese)
  - esito piano (approvato/rifiutato): email al dipendente
  - esito variazione (approvata/rifiutata): email al dipendente

Comando promemoria:

```bash
python manage.py send_submission_reminders
```

Opzioni utili:

```bash
python manage.py send_submission_reminders --dry-run
python manage.py send_submission_reminders --force
python manage.py send_submission_reminders --date 2026-03-30 --dry-run
python manage.py send_manager_monthly_summary --dry-run
python manage.py send_manager_monthly_summary --force
python manage.py send_manager_monthly_summary --date 2026-04-01 --dry-run
python manage.py prepare_next_year_holidays --dry-run
python manage.py prepare_next_year_holidays --force --year 2027
```

Esecuzione schedulata consigliata (cron giornaliero, il comando invia solo l'ultimo giorno):

```cron
15 8 * * * cd /app && python manage.py send_submission_reminders
```

## Vincoli di business implementati

- Limite giorni lavoro agile: massimo 10 giorni/mese
- Eccezione febbraio: massimo 8 giorni
- Prevalenza presenza: se sono presenti giorni `REMOTE`, i giorni `ON_SITE` devono essere strettamente maggiori
- Sono ammessi solo giorni lavorativi (lun-ven): weekend non consentiti nel piano
- Le festivita nazionali italiane sono riconosciute automaticamente e non possono essere usate nel piano
- Le festivita configurate manualmente (globali o per reparto) non possono essere usate nel piano
- Nel portale i giorni festivi del mese sono esclusi dal calendario compilabile
- Modifica calendario: mese corrente e mese successivo
- Mese corrente: solo richiesta variazione con motivazione (non invio in approvazione)

I vincoli sono validati sia in fase di creazione/modifica del piano, sia al momento dell'invio (`submit`).

## Configurazione per reparto

Dalla Pagina di Amministrazione puoi configurare:

- `DepartmentPolicy`: override dei limiti per singolo reparto
  - `max_remote_days`
  - `february_max_remote_days`
  - `require_on_site_prevalence`
- `Holiday`: festivita globali (campo reparto vuoto) o specifiche per reparto

## Anagrafica utente e referente

Nella Pagina di Amministrazione, nella scheda utente (`Users`), sono disponibili:
- `Afferenza territoriale` (campo tecnico: `department`)
- `Ruolo` (`EMPLOYEE`, `ADMIN`, `SUPERADMIN`)
- `Responsabile approvazione` (campo tecnico: `manager`)
- `Sottoscrizione AILA` (`aila_subscribed`), scelta `No`/`Si` (default `No`)
- `Approvazione automatica` (`auto_approve`), scelta `No`/`Si` (default `No`)

Note:
- il referente puo essere assegnato solo a utenti con ruolo `ADMIN`/`SUPERADMIN` (o superuser)
- per utenti `ADMIN`/`SUPERADMIN` (o superuser), il referente puo essere solo se stesso (oppure vuoto)
- se `Sottoscrizione AILA=No`, l'utente non puo creare/modificare/inviare piani o richieste variazione
- se `Sottoscrizione AILA=No` ma l'utente e `ADMIN`/`SUPERADMIN`, puo comunque accedere e operare nelle code approvazioni/variazioni
- se `Approvazione automatica=Si`, invio piano e richieste variazione vengono approvati direttamente senza passare dalle code

## Ruoli e permessi (Django vs App)

Per evitare ambiguita, i livelli sono due:

1. Ruolo applicativo (`role`):
   - `EMPLOYEE`: utente standard
   - `ADMIN` (Responsabile approvazione): gestisce code approvazione/variazione per utenti assegnati
   - `SUPERADMIN`: visione/operativita globale nell'applicazione

2. Permessi Django (`is_staff`, `is_superuser`):
   - `is_staff`: accesso all'interfaccia Pagina di Amministrazione
   - `is_superuser`: privilegi massimi Pagina di Amministrazione

Comportamento nel portale applicativo:
- un utente `is_superuser=True` viene trattato come super admin anche nell'app (equivalente operativo a `SUPERADMIN`)
- l'accesso a code approvazione/variazioni dipende dal ruolo applicativo (`ADMIN`/`SUPERADMIN`), non dal flag `is_staff`

Allineamento automatico implementato:
- `is_superuser=True` forza automaticamente `role=SUPERADMIN` e `is_staff=True`
- `role=SUPERADMIN` forza `is_staff=True`
- `role=ADMIN` mantiene `is_staff=False` (resta approvatore nell'app ma senza accesso Pagina di Amministrazione)
- utente `EMPLOYEE` non superuser viene riallineato con `is_staff=False`

### Sync automatico festivita nazionali

Puoi precaricare nel DB le festivita nazionali italiane:

```bash
python manage.py sync_holidays --year 2026
```

Per aggiornare anche nomi gia esistenti nello stesso giorno:

```bash
python manage.py sync_holidays --year 2026 --overwrite
```

## Limiti attuali (da discutere)

- Gestione utenti/gruppi avanzata delegata alla Pagina di Amministrazione
- Notifiche email di base (template modificabili via admin)
- Nessun frontend SPA separato (UI server-rendered)

## Licenza

Questo progetto e distribuito con licenza **GNU GPL v3.0 o successiva (GPL-3.0-or-later)**.
Per i dettagli completi, vedi il file [`LICENSE`](LICENSE).

## Nota su Codex

Durante lo sviluppo e la manutenzione puo essere utilizzato **Codex** come strumento di supporto tecnico (analisi, proposta modifiche, automazione operativa).
Le decisioni progettuali e la validazione finale del codice restano comunque in carico ai responsabili del progetto.
