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

Formato data nel portale:
- `AGILE_DATE_DISPLAY_FORMAT=IT` -> `gg/mm/aaaa` (default)
- `AGILE_DATE_DISPLAY_FORMAT=ISO` -> `aaaa-mm-gg`

Logo nella schermata login (opzionale):
- `AGILE_LOGIN_LOGO_URL=` URL assoluto dell'immagine (es. `https://.../logo.png`)
- se vuoto, il logo non viene mostrato

3. Avvia:

```bash
docker compose up --build
```

4. App disponibile su:
- Portale dipendenti: `http://localhost:8001/`
- API: `http://localhost:8001/api/`
- Admin: `http://localhost:8001/admin/`

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

Per passare dalla versione precedente di `Lagile.management` a questa versione:

1. importare gli utenti dall'LDAP di Istituto:

```bash
python manage.py import_ldap_users
```

2. dalla versione precedente, accedere come `superuser`, aprire `Setting -> Importa utenti` e scaricare il CSV
3. usare il CSV scaricato per allineare sedi/flag utente su questa versione:

```bash
python manage.py update_user_sites_from_csv /percorso/file.csv --site-column department --site-mode last-word
```

In alternativa, i due passaggi sono disponibili anche da Django Admin:
- URL: `/admin/agile/import-tools/`
- accesso: solo `superuser`

### Aggiornamento sede utenti da CSV (match su email)

Nota: questo script e pensato esclusivamente per la migrazione dati dalla versione precedente di `Lagile.management`.
Procedura consigliata dalla versione precedente:
- accedere come `superuser`
- aprire `Setting -> Importa utenti`
- scaricare il file CSV da utilizzare per l'import

Puoi aggiornare in batch la `Sede` degli utenti locali con:

```bash
python manage.py update_user_sites_from_csv /percorso/file.csv
```

Assunzioni default:
- colonna email: `email`
- colonna sede: `sede`
- delimitatore: `,`

Opzioni utili:

```bash
python manage.py update_user_sites_from_csv /percorso/file.csv --delimiter ';'
python manage.py update_user_sites_from_csv /percorso/file.csv --email-column mail --site-column site
python manage.py update_user_sites_from_csv /percorso/file.csv --site-column department --site-mode last-word
python manage.py update_user_sites_from_csv /percorso/file.csv --fallback-lastname --lastname-column lastname
python manage.py update_user_sites_from_csv /percorso/file.csv --fallback-lastname --lastname-column lastname --firstname-column name
python manage.py update_user_sites_from_csv /percorso/file.csv --site-column department --site-mode last-word --import-groups
python manage.py update_user_sites_from_csv /percorso/file.csv --dry-run
```

Note:
- logica match import CSV:
  1) `email CSV == email DB` -> importa
  2) se email non trova match, prova `lastname CSV == lastname DB` -> importa se univoco
  3) se non risolto, prova `lastname CSV` contenuto in `email DB` -> importa se univoco
- quando i match su cognome risultano ambigui, viene usato `name` (colonna configurabile con `--firstname-column`) per disambiguare su `first_name`
- se anche dopo il controllo sul nome il match resta ambiguo, la riga viene segnalata e ignorata
- i confronti su cognome/nome/email nel fallback ignorano le lettere accentate (es. `Rossi` = `Ròssi`)
- con `--import-groups`, la prima parola di `department` viene usata come nome gruppo Django:
  - il gruppo viene creato se non esiste
  - l'utente viene associato al gruppo
- vengono accettate solo sedi presenti in `AGILE_SITES`
- con `--site-mode last-word` la sede viene estratta come ultima parola del campo sorgente (es. `Ufficio Ricerca Napoli` -> `Napoli`)
- se il campo sorgente sede contiene `Default`, la riga viene ignorata
- quando la sede viene impostata correttamente, il comando imposta anche `Sottoscrizione AILA` a `Si`
- quando la sede viene impostata correttamente, il comando imposta anche `is_active=Si`
- regole automatiche per referente/auto-approvazione per sede:
  - `Napoli` -> referente `direttore`, `auto_approve=Si`
  - `Catania` -> referente `nicola.dantona`, `auto_approve=No`
  - `Sassari` -> referente `Pietro Spanu`, `auto_approve=No`
  - `Padova` -> referente `Paolo ruzza`, `auto_approve=No`
- se un utente viene usato come referente da queste regole e non e gia `ADMIN`/`SUPERADMIN`, viene impostato a ruolo `Referente Amministrativo` (`ADMIN`)
- il comando stampa un report finale con aggiornati/invariati/non trovati/sedi non valide

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
```

Nota: in assenza di configurazione SMTP resta il backend console (`EMAIL_BACKEND` di default), utile in sviluppo.

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
- un utente `is_staff=True` viene considerato approvatore anche se `role` non e `ADMIN`

Allineamento automatico implementato:
- `is_superuser=True` forza automaticamente `role=SUPERADMIN` e `is_staff=True`
- `role=SUPERADMIN` o `role=ADMIN` forza `is_staff=True`
- `is_staff=True` con `role=EMPLOYEE` riallinea automaticamente a `role=ADMIN`
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
