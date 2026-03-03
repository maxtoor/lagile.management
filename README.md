# Gestione Lavoro Agile (MVP)

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
- Scheda utente nel portale con `Nome e cognome`, `Sede` e `Referente amministrativo`
- Gli approvatori possono aprire il dettaglio giornaliero del piano prima di approvare/rifiutare
- Invio email automatico al dipendente quando il piano viene approvato o rifiutato
- I dipendenti possono modificare il piano del mese corrente e del mese successivo; il mese corrente non e inviabile in approvazione ma solo in richiesta variazione

## Stack

- Python 3.12
- Django 5 + Django REST Framework
- PostgreSQL 16
- LDAP opzionale con `django-auth-ldap`

## Perche Django

La scelta di Django e stata fatta per motivi pratici:

- copre in modo nativo autenticazione, ruoli, amministrazione e workflow applicativi
- semplifica la gestione on-premise su Linux con stack stabile e noto
- con il numero di utenti coinvolti, non e necessario introdurre architetture piu complesse
- il Django Admin riduce sviluppo custom per gestione utenti, referenti, import e template email
- facilita manutenzione e evoluzione delle regole di business lato server

## Avvio rapido (Docker)

1. Copia variabili ambiente:

```bash
cp .env.example .env
```

2. Imposta almeno queste variabili in `.env`:

```env
DJANGO_SECRET_KEY=una-chiave-forte
DEBUG=1
AGILE_SITES=Napoli,Catania,Sassari,Padova
AGILE_DATE_DISPLAY_FORMAT=IT
AGILE_LOGIN_LOGO_URL=https://example.org/static/logo-istituto.png
POSTGRES_DB=agile_work
POSTGRES_USER=agile
POSTGRES_PASSWORD=agile
POSTGRES_HOST=db
POSTGRES_PORT=5432
LDAP_ENABLED=0
```

`ALLOWED_HOSTS` (Django):
- definisce gli hostname/domini autorizzati a raggiungere l'applicazione
- richieste con `Host` non presente in elenco vengono rifiutate (`DisallowedHost`)
- sviluppo locale tipico: `ALLOWED_HOSTS=localhost,127.0.0.1`
- produzione: inserire i domini/IP reali esposti (es. `lagile.example.org,10.0.0.15`)

Formato data nel portale:
- `AGILE_DATE_DISPLAY_FORMAT=IT` -> `gg/mm/aaaa` (default)
- `AGILE_DATE_DISPLAY_FORMAT=ISO` -> `aaaa-mm-gg`

Logo nella schermata login (opzionale):
- `AGILE_LOGIN_LOGO_URL=` URL assoluto dell'immagine (es. `https://.../logo.png`)
- se vuoto, il logo non viene mostrato

Log applicativo e monitor admin:
- `AGILE_LOG_FILE=/app/logs/agile.log` file log principale
- `AGILE_LOG_LEVEL=INFO` livello log
- `AGILE_LOG_MONITOR_FILE=/app/logs/agile.log` file mostrato nel monitor admin
- `AGILE_LOG_MONITOR_SOURCES=app:/app/logs/agile.log;scheduler:/app/logs/scheduler.log` sorgenti selezionabili
- `AGILE_LOG_MONITOR_REFRESH_SECONDS=8` intervallo refresh monitor

3. Avvia:

```bash
docker compose up --build
```

4. App disponibile su:
- Portale dipendenti: `http://localhost:8001/`
- API: `http://localhost:8001/api/`
- Admin: `http://localhost:8001/admin/`

Nota Docker:
- e presente un servizio `scheduler` che esegue periodicamente:
  - `send_submission_reminders` (promemoria utente ultimo giorno mese)
  - `send_manager_monthly_summary` (riepilogo referente primo giorno mese)
- intervallo controllo configurabile con `REMINDER_CHECK_INTERVAL_SECONDS` (default `86400`)
- i comandi inviano realmente email solo nel loro giorno previsto (a meno di `--force`)
- in Django Admin e disponibile il link `Monitor log` per visualizzare il tail live e selezionare la sorgente (es. `app` / `scheduler`)

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
- il campo `Sede` viene valorizzato solo se il valore LDAP e tra quelli ammessi da `AGILE_SITES`, altrimenti resta vuoto

## Migrazione dalla versione precedente

Nota: questa procedura riguarda esclusivamente gli Istituti del CNR che avevano adottato la versione precedente di questo software.

Dettagli operativi nel documento dedicato:
- [`docs/migrazione_cnr.md`](/Users/master/Documents/projects/lagile.new/agile_work/docs/migrazione_cnr.md)

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
```

Nota: in assenza di configurazione SMTP resta il backend console (`EMAIL_BACKEND` di default), utile in sviluppo.
Se `AGILE_EMAIL_FROM_NAME` e valorizzato, il mittente viene inviato nel formato `Nome <indirizzo>`.

Template email modificabili da Django admin:
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

Da Django Admin puoi configurare:

- `DepartmentPolicy`: override dei limiti per singolo reparto
  - `max_remote_days`
  - `february_max_remote_days`
  - `require_on_site_prevalence`
- `Holiday`: festivita globali (campo reparto vuoto) o specifiche per reparto

## Anagrafica utente e referente

In Django Admin, nella scheda utente (`Users`), sono disponibili:
- `Sede` (campo tecnico: `department`)
- `Ruolo` (`EMPLOYEE`, `ADMIN`, `SUPERADMIN`)
- `Referente amministrativo` (campo tecnico: `manager`)
- `Sottoscrizione AILA` (`aila_subscribed`), scelta `No`/`Si` (default `No`)
- `Approvazione automatica` (`auto_approve`), scelta `No`/`Si` (default `No`)

Note:
- il referente puo essere assegnato solo a utenti con ruolo `ADMIN`/`SUPERADMIN` (o superuser)
- un utente non puo essere referente di se stesso
- se `Sottoscrizione AILA=No`, l'utente non puo creare/modificare/inviare piani o richieste variazione
- se `Sottoscrizione AILA=No` ma l'utente e `ADMIN`/`SUPERADMIN`, puo comunque accedere e operare nelle code approvazioni/variazioni
- se `Approvazione automatica=Si`, invio piano e richieste variazione vengono approvati direttamente senza passare dalle code

## Ruoli e permessi (Django vs App)

Per evitare ambiguita, i livelli sono due:

1. Ruolo applicativo (`role`):
   - `EMPLOYEE`: utente standard
   - `ADMIN` (Referente amministrativo): gestisce code approvazione/variazione per utenti assegnati
   - `SUPERADMIN`: visione/operativita globale nell'applicazione

2. Permessi Django (`is_staff`, `is_superuser`):
   - `is_staff`: accesso all'interfaccia Django admin
   - `is_superuser`: privilegi massimi Django admin

Comportamento nel portale applicativo:
- un utente `is_superuser=True` viene trattato come super admin anche nell'app (equivalente operativo a `SUPERADMIN`)
- l'accesso a code approvazione/variazioni dipende dal ruolo applicativo (`ADMIN`/`SUPERADMIN`), non dal flag `is_staff`

Allineamento automatico implementato:
- `is_superuser=True` forza automaticamente `role=SUPERADMIN` e `is_staff=True`
- `role=SUPERADMIN` forza `is_staff=True`
- `role=ADMIN` mantiene `is_staff=False` (resta approvatore nell'app ma senza accesso Django Admin)
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

- Gestione utenti/gruppi avanzata delegata al Django Admin
- Notifiche email di base (template modificabili via admin)
- Nessun frontend SPA separato (UI server-rendered)

## Licenza

Questo progetto e distribuito con licenza **GNU GPL v3.0 o successiva (GPL-3.0-or-later)**.
Per i dettagli completi, vedi il file [`LICENSE`](/Users/master/Documents/projects/lagile.new/agile_work/LICENSE).

## Nota su Codex

Durante lo sviluppo e la manutenzione puo essere utilizzato **Codex** come strumento di supporto tecnico (analisi, proposta modifiche, automazione operativa).
Le decisioni progettuali e la validazione finale del codice restano comunque in carico ai responsabili del progetto.
