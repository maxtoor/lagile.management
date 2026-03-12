# Gestione Lavoro Agile

Applicazione on-premise per pianificazione e approvazione del lavoro agile. Versione 2.0.0.

Backend Django per gestione mensile del calendario di lavoro agile con autenticazione LDAP o locale, workflow di approvazione e audit log.

## Panoramica

- Login con token (`/api/auth/login/`) usando backend locale o LDAP
- Gestione utenti con ruoli: `EMPLOYEE`, `ADMIN`, `SUPERADMIN`
- Piano mensile per dipendente (`MonthlyPlan`) con dettaglio giornaliero (`PlanDay`)
- Workflow: `DRAFT -> SUBMITTED -> APPROVED/REJECTED`
- Revisione da parte degli amministratori
- Tracciamento eventi principali in `AuditLog`
- Pannello amministrativo Django (`/admin/`)
- Portale web unico con area dipendente e coda approvazioni per `ADMIN`/`SUPERADMIN`
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

1. Crea la directory applicazione, scarica il progetto ed entra nella cartella:

```bash
mkdir -p /opt/containers
git clone https://github.com/maxtoor/lagile.management.git /opt/containers/lagile-management
cd /opt/containers/lagile-management
```

2. Copia variabili ambiente:

```bash
cp .env.example .env
```

3. Imposta almeno queste variabili in `.env`:

```env
DJANGO_SECRET_KEY=una-chiave-forte
DEBUG=1
ALLOWED_HOSTS=localhost,127.0.0.1
TIME_ZONE=Europe/Rome

AGILE_SITES=Sede principale
AGILE_DATE_DISPLAY_FORMAT=IT

POSTGRES_DB=agile_work
POSTGRES_USER=agile
POSTGRES_PASSWORD=agile
POSTGRES_HOST=db
POSTGRES_PORT=5432

LDAP_ENABLED=0
AGILE_PUBLIC_BASE_URL=http://localhost:8001
```

Per la configurazione completa delle variabili ambiente:
- vedi la sezione `Configurazione`
- oppure il dettaglio completo in [`docs/variabili_env.md`](docs/variabili_env.md)

4. Avvia:

```bash
docker compose up --build
```

5. App disponibile su:
- Portale dipendenti: `http://localhost:8001/`
- API: `http://localhost:8001/api/`
- Admin: `http://localhost:8001/admin/`

Per installazione automatica e upgrade via script:
- `scripts/install.sh`
- `scripts/upgrade.sh`

Esempi rapidi:

```bash
# Installazione automatica
bash scripts/install.sh --install-dir /opt/containers/lagile-management --branch main --port 8001

# Simulazione installazione
bash scripts/install.sh --dry-run

# Upgrade
bash scripts/upgrade.sh
```

Nota Docker:
- e presente un servizio `scheduler`; dettagli operativi nella sezione `Automazioni`
- nella Pagina di Amministrazione e disponibile il link `Monitor log` per visualizzare il tail live e selezionare la sorgente (es. `app` / `scheduler`)

## Avvio locale (senza Docker)

Requisiti minimi:
- Python 3.12
- PostgreSQL 16

Nota:
- il percorso consigliato e Docker
- l'avvio locale senza Docker e adatto soprattutto a sviluppo o troubleshooting su host gia predisposti

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
set -a
source .env
set +a
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

## Configurazione

### Logo di login

Puoi personalizzare il logo della pagina di login tramite:

```env
AGILE_LOGIN_LOGO_URL=https://example.org/static/logo-istituto.png
```

Comportamento:
- se `AGILE_LOGIN_LOGO_URL` e valorizzata, viene usato quel logo
- se `AGILE_LOGIN_LOGO_URL` e vuota o assente, viene usato il logo di default incluso nell'applicazione (`informatici_cnr.png`)

### LDAP

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

#### Registrazione automatica al primo login (flusso ordinario)

Con LDAP attivo, il comportamento ordinario dell'applicazione non e l'importazione massiva preventiva, ma la creazione automatica dell'utente locale al primo login LDAP riuscito.

In pratica:
- l'utente inserisce le proprie credenziali LDAP nel portale
- se l'autenticazione LDAP riesce e l'utente non esiste ancora nel database locale, viene creato automaticamente
- il record locale viene inizializzato con password non utilizzabile e configurazione applicativa minima
- l'utente puo entrare nel portale, ma resta in onboarding finche non viene completata la configurazione applicativa

Alla prima registrazione automatica:
- viene inviata una email ai superuser
- la email contiene i link al portale e alla Pagina di Amministrazione
- il superuser deve completare i campi applicativi necessari, in particolare:
  - `Attivo`
  - `Afferenza territoriale`
  - `Responsabile approvazione`
  - `Sottoscrizione AILA`
  - eventuali altre impostazioni locali

Questo approccio e il piu adatto quando LDAP e la sorgente autorevole per l'identita utente:
- evita precaricamenti massivi non necessari
- crea gli account locali solo quando servono davvero
- mantiene su LDAP autenticazione e anagrafica base
- lascia all'applicazione solo i dati funzionali specifici del dominio

In sintesi:
- con LDAP attivo, la registrazione automatica al primo login e il flusso standard
- `import_ldap_users` e `sync_ldap_users` sono strumenti opzionali di supporto operativo, non un prerequisito per il funzionamento normale

#### Controllo periodico presenza utenti in LDAP

Per il controllo periodico degli utenti gia registrati localmente e disponibile un comando separato.
Vedi anche la sezione `Comandi amministrativi`.

Questo comando:
- prende in considerazione solo gli utenti locali attivi gestiti via LDAP
- verifica per ciascuno se esiste ancora nella directory LDAP usando `LDAP_USER_FILTER`
- se l'utente non esiste piu, lo imposta `is_active=False`
- registra un audit log applicativo
- invia una email riepilogativa ai superuser con l'elenco degli utenti disattivati

Questo e il comando piu adatto all'esecuzione periodica via scheduler.
Non aggiorna nome, cognome o email, e non crea utenti mancanti.

#### Import utenti LDAP in locale (non attivi)

Per importare utenti LDAP nel DB locale e gestirli manualmente, vedi la sezione `Comandi amministrativi`.

Note:
- gli utenti importati (nuovi o aggiornati) vengono impostati `is_active=False`
- agli utenti importati viene impostata password locale non utilizzabile
- il campo `Afferenza territoriale` viene valorizzato solo se il valore LDAP e tra quelli ammessi da `AGILE_SITES`, altrimenti resta vuoto

#### Sync periodico utenti LDAP (allineamento)

Per allineare gli utenti gia importati quando LDAP cambia, vedi la sezione `Comandi amministrativi`.

Regole sync:
- chiave di allineamento: `username`
- campi aggiornati dal sync: `first_name`, `last_name`, `email`
- campi non toccati: `Afferenza territoriale`, `Responsabile approvazione`, `Sottoscrizione AILA`, `Ruolo`, `Auto-approvazione`
- gli account locali con password utilizzabile non vengono modificati
- non e il comando pensato per il controllo periodico di presenza LDAP: per quello usare `check_ldap_user_presence`
- per default non crea utenti mancanti (evita import massivo involontario)
- con `--create-missing` crea in locale gli utenti LDAP assenti nel DB
- con `--deactivate-missing` vengono disattivati gli account LDAP locali non piu presenti su LDAP (solo account con password non utilizzabile)

### Email notifiche

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
  - `LDAP_USER_IMPORTED`
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
  - `{email}`, `{import_timestamp}`
  - `{public_base_url}`, `{portal_url}`, `{admin_url}`
  - `{change_reason}`, `{rejection_reason}`, `{final_line}`
- dalla scheda template e disponibile il pulsante `Invia email di test` con anteprima e invio verso destinatario scelto
- eventi email principali:
  - primo login LDAP di un utente non ancora presente in locale: email ai superuser per completare onboarding e configurazione applicativa
  - invio richiesta variazione: email al responsabile approvazione dell'utente
  - esito piano (approvato/rifiutato): email al dipendente
  - esito variazione (approvata/rifiutata): email al dipendente

Le email periodiche sono gestite dal servizio `scheduler`; vedi la sezione dedicata `Automazioni`.

Per l'esecuzione manuale dei comandi email, vedi la sezione `Comandi amministrativi`.

Se usi Docker non serve un cron esterno: questi comandi vengono gia eseguiti automaticamente dal servizio `scheduler`.

Se invece vuoi eseguirli fuori Docker, puoi schedularli via cron. Esempio:

```cron
15 8 * * * cd /app && python manage.py send_submission_reminders
20 8 * * * cd /app && python manage.py send_manager_monthly_summary
```

## Funzionamento applicativo

### Vincoli di business implementati

- Limite giorni lavoro agile: massimo 10 giorni/mese
- Eccezione febbraio: massimo 8 giorni
- Prevalenza presenza: se sono presenti giorni `REMOTE`, i giorni `ON_SITE` devono essere strettamente maggiori
- Sono ammessi solo giorni lavorativi (lun-ven): weekend non consentiti nel piano
- Le festivita nazionali italiane sono riconosciute automaticamente e non possono essere usate nel piano
- Le festivita configurate manualmente (globali o per afferenza territoriale) non possono essere usate nel piano
- Nel portale i giorni festivi del mese sono esclusi dal calendario compilabile
- Modifica calendario: mese corrente e mese successivo
- Mese corrente: solo richiesta variazione con motivazione (non invio in approvazione)

I vincoli sono validati sia in fase di creazione/modifica del piano, sia al momento dell'invio (`submit`).

### Configurazione per Afferenza territoriale (eventuali sedi distaccate)

Dalla Pagina di Amministrazione puoi configurare:

- `DepartmentPolicy`: override dei limiti per singola afferenza territoriale
  - `max_remote_days`
  - `february_max_remote_days`
  - `require_on_site_prevalence`
- `Holiday`: festivita globali (campo afferenza territoriale vuoto) o specifiche per afferenza territoriale

### Anagrafica utente e referente

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

### Ruoli e permessi (Django vs App)

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

#### Sync automatico festivita nazionali

Puoi precaricare nel DB le festivita nazionali italiane:
- dalla Pagina di Amministrazione, tramite gli strumenti dedicati
- oppure da riga di comando

Per i comandi CLI, vedi la sezione `Comandi amministrativi`.

#### Preparazione festivita anno successivo

Per predisporre automaticamente le festivita dell'anno successivo e inviare un report ai superuser, vedi la sezione `Comandi amministrativi`.

Note:
- il comando genera o aggiorna le festivita nazionali italiane dell'anno indicato
- in ambiente Docker viene eseguito automaticamente dal servizio `scheduler` il 1 dicembre
- il report finale viene inviato ai superuser via email
- puo comunque essere eseguito manualmente quando serve

## Automazioni

Nel deploy Docker e presente un servizio `scheduler` che esegue periodicamente alcuni comandi applicativi.

Intervallo di controllo:
- configurabile con `REMINDER_CHECK_INTERVAL_SECONDS`
- fallback in `docker-compose.yml`: `3600` secondi

Job attuali:
- `send_submission_reminders`
  - promemoria ultimo giorno del mese per l'invio del piano del mese successivo
  - invia email agli utenti attivi senza auto-approvazione che non hanno ancora stato `SUBMITTED` o `APPROVED`
- `send_manager_monthly_summary`
  - riepilogo il primo giorno del mese per i responsabili approvazione
  - include piani in attesa, piani approvati, utenti senza piano e utenti in auto-approvazione
- `prepare_next_year_holidays`
  - il 1 dicembre prepara le festivita dell'anno successivo
  - invia un report ai superuser
- `check_ldap_user_presence`
  - verifica periodicamente se gli utenti locali gestiti via LDAP esistono ancora nella directory
  - se un utente non esiste piu, lo disattiva e invia un report ai superuser

Note operative:
- il loop esegue i comandi a ogni intervallo, ma ciascun comando applica internamente le proprie condizioni temporali
- i comandi che lavorano su date specifiche non inviano nulla fuori finestra, salvo uso esplicito di `--force`
- nella Pagina di Amministrazione e disponibile il monitor log per controllare il comportamento del servizio

## Comandi amministrativi

Riepilogo dei principali comandi manuali/amministrativi disponibili.

LDAP:
- `python manage.py import_ldap_users`
- `python manage.py import_ldap_users --dry-run`
- `python manage.py import_ldap_users --base-dn "ou=people,dc=example,dc=org" --filter "(objectClass=person)"`
- `python manage.py sync_ldap_users`
- `python manage.py sync_ldap_users --dry-run`
- `python manage.py sync_ldap_users --deactivate-missing`
- `python manage.py sync_ldap_users --create-missing`
- `python manage.py check_ldap_user_presence`
- `python manage.py check_ldap_user_presence --dry-run`

Email operative:
- `python manage.py send_submission_reminders`
- `python manage.py send_submission_reminders --dry-run`
- `python manage.py send_submission_reminders --force`
- `python manage.py send_submission_reminders --date 2026-03-30 --dry-run`
- `python manage.py send_manager_monthly_summary`
- `python manage.py send_manager_monthly_summary --dry-run`
- `python manage.py send_manager_monthly_summary --force`
- `python manage.py send_manager_monthly_summary --date 2026-04-01 --dry-run`

Festivita:
- `python manage.py sync_holidays --year 2026`
- `python manage.py sync_holidays --year 2026 --overwrite`
- `python manage.py prepare_next_year_holidays --dry-run`
- `python manage.py prepare_next_year_holidays --force --year 2027`

Import/export release:
- `python manage.py export_release_data ./release-export.json`
- `python manage.py import_release_data ./release-export.json --dry-run`
- `python manage.py import_release_data ./release-export.json --mode merge`
- `python manage.py import_release_data ./release-export.json --mode replace`

## Operazioni straordinarie

### Import/Export release (JSON)

Per trasferire configurazione e anagrafica base tra installazioni (es. bootstrap nuova istanza) sono disponibili i comandi riepilogati nella sezione `Comandi amministrativi`.

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

### Migrazione dalla versione precedente

Nota: questa procedura riguarda esclusivamente gli Istituti del CNR che avevano adottato la versione precedente di questo software.

Dettagli operativi nel documento dedicato:
- [`docs/migrazione_cnr.md`](docs/migrazione_cnr.md)

## API

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

## Licenza

Questo progetto e distribuito con licenza **GNU GPL v3.0 o successiva (GPL-3.0-or-later)**.
Per i dettagli completi, vedi il file [`LICENSE`](LICENSE).

## Nota su Codex

Durante lo sviluppo e la manutenzione puo essere utilizzato **Codex** come strumento di supporto tecnico (analisi, proposta modifiche, automazione operativa).
Le decisioni progettuali e la validazione finale del codice restano comunque in carico ai responsabili del progetto.
