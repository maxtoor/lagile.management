# Variabili `.env`

Questo documento descrive tutte le variabili ambiente supportate dal progetto.

## Core applicazione

| Variabile | Obbligatoria | Default | Descrizione |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | Si | `dev-secret-change-me` | Chiave segreta Django. In produzione deve essere robusta e privata. |
| `DEBUG` | No | `0` | `1` abilita debug Django (solo sviluppo). |
| `ALLOWED_HOSTS` | Si | `localhost,127.0.0.1` | Hostname/domini ammessi (separati da virgola). |
| `TIME_ZONE` | No | `Europe/Rome` | Fuso orario applicazione. |
| `AGILE_SITES` | No | `Sede principale` | Elenco afferenze territoriali ammesse (CSV). Esempio multi-sede: `Napoli,Catania,Sassari,Padova`. |
| `AGILE_DATE_DISPLAY_FORMAT` | No | `IT` | Formato data nel portale (`IT` o `ISO`). |
| `AGILE_LOGIN_LOGO_URL` | No | vuoto | URL assoluto logo schermata login. |
| `AGILE_FAVICON_URL` | No | vuoto | URL assoluto favicon applicazione. |
| `AGILE_COMPANY_NAME` | No | `LAgile.Management` | Nome compagnia mostrato nel footer. |
| `AGILE_COPYRIGHT_YEAR` | No | `2026` | Anno mostrato nel footer. |
| `ICB_LEGACY` | No | `0` | `1` mostra negli Strumenti admin la sezione legacy CSV ICB; `0` la nasconde e blocca le azioni CSV ICB. |

## Database PostgreSQL

| Variabile | Obbligatoria | Default | Descrizione |
|---|---|---|---|
| `POSTGRES_DB` | No | `agile_work` | Nome database. |
| `POSTGRES_USER` | No | `agile` | Utente DB. |
| `POSTGRES_PASSWORD` | Si | `agile` | Password DB. Cambiare in produzione. |
| `POSTGRES_HOST` | No | `127.0.0.1` | Host DB (in Docker: `db`). |
| `POSTGRES_PORT` | No | `5432` | Porta DB. |

## LDAP

| Variabile | Obbligatoria | Default | Descrizione |
|---|---|---|---|
| `LDAP_ENABLED` | No | `0` | `1` abilita autenticazione LDAP. |
| `LDAP_SERVER_URI` | Si se `LDAP_ENABLED=1` | `ldap://localhost:389` | URI server LDAP. |
| `LDAP_BIND_DN` | Si se `LDAP_ENABLED=1` | vuoto | DN utente tecnico bind LDAP. |
| `LDAP_BIND_PASSWORD` | Si se `LDAP_ENABLED=1` | vuoto | Password bind LDAP. |
| `LDAP_USER_BASE_DN` | Si se `LDAP_ENABLED=1` | `dc=example,dc=org` | Base DN ricerca utenti. |
| `LDAP_USER_FILTER` | No | `(uid=%(user)s)` | Filtro ricerca utente in login. |
| `LDAP_ATTR_USERNAME` | No | `uid` | Attributo username LDAP. |
| `LDAP_ATTR_FIRST_NAME` | No | `givenName` | Attributo nome LDAP. |
| `LDAP_ATTR_LAST_NAME` | No | `sn` | Attributo cognome LDAP. |
| `LDAP_ATTR_EMAIL` | No | `mail` | Attributo email LDAP. |
| `LDAP_ATTR_DEPARTMENT` | No | `ou` | Attributo afferenza territoriale/reparto LDAP (import). |
| `LDAP_IMPORT_FILTER` | No | `(objectClass=person)` | Filtro default comandi `import_ldap_users` e `sync_ldap_users`. |

## Email/SMTP

| Variabile | Obbligatoria | Default | Descrizione |
|---|---|---|---|
| `EMAIL_BACKEND` | No | `django.core.mail.backends.console.EmailBackend` | Backend email Django. Nota: il fallback reale del codice e `console`, mentre `.env.example` propone `django.core.mail.backends.smtp.EmailBackend` come configurazione SMTP tipica. |
| `EMAIL_HOST` | Si per SMTP reale | `localhost` | Host SMTP. |
| `EMAIL_PORT` | No | `25` | Porta SMTP. |
| `EMAIL_HOST_USER` | No | vuoto | Utente SMTP. |
| `EMAIL_HOST_PASSWORD` | No | vuoto | Password SMTP. |
| `EMAIL_USE_TLS` | No | `0` | `1` abilita STARTTLS. |
| `EMAIL_USE_SSL` | No | `0` | `1` abilita SSL SMTP. |
| `DEFAULT_FROM_EMAIL` | No | `noreply@istituto.local` | Mittente email. |
| `AGILE_EMAIL_FROM_NAME` | No | vuoto | Nome mittente (formato `Nome <email>`). |
| `AGILE_EMAIL_REDIRECT_TO` | No | vuoto | Se valorizzata, tutte le email in uscita vengono reindirizzate a questa casella (o lista CSV) invece che ai destinatari reali. Utile in sviluppo/test. |
| `AGILE_PUBLIC_BASE_URL` | No | vuoto | URL pubblico base dell'applicazione (es. `https://lagile.example.org`). Se valorizzata, viene usata per inserire link al portale o all'admin nelle email di comunicazione. |

## Logging e monitor admin

| Variabile | Obbligatoria | Default | Descrizione |
|---|---|---|---|
| `AGILE_LOG_FILE` | No | `/app/logs/agile.log` | File log applicazione. |
| `AGILE_LOG_LEVEL` | No | `INFO` | Livello log (`DEBUG`, `INFO`, ...). |
| `AGILE_LOG_MONITOR_FILE` | No | uguale a `AGILE_LOG_FILE` | File principale mostrato nel monitor admin. |
| `AGILE_LOG_MONITOR_SOURCES` | No | `app:/app/logs/agile.log;scheduler:/app/logs/scheduler.log` | Sorgenti selezionabili nel monitor (`chiave:percorso;...`). |
| `AGILE_LOG_MONITOR_REFRESH_SECONDS` | No | `8` | Intervallo refresh monitor log admin. |

## Scheduler reminder/sommari

| Variabile | Obbligatoria | Default | Descrizione |
|---|---|---|---|
| `REMINDER_CHECK_INTERVAL_SECONDS` | No | `3600` (compose fallback) | Intervallo loop container `scheduler`. Tipico: `86400` (1 giorno). |

## Variabili opzionali per bootstrap superuser (Docker)

Il container `web` esegue `python manage.py createsuperuser --noinput`.
Per evitare messaggi di errore ad ogni avvio, puoi impostare:

| Variabile | Obbligatoria | Default | Descrizione |
|---|---|---|---|
| `DJANGO_SUPERUSER_USERNAME` | No | - | Username superuser iniziale. |
| `DJANGO_SUPERUSER_EMAIL` | No | - | Email superuser iniziale. |
| `DJANGO_SUPERUSER_PASSWORD` | No | - | Password superuser iniziale. |

## Sicurezza

- Non versionare `.env` con credenziali reali.
- In produzione usare valori robusti per `DJANGO_SECRET_KEY`, password DB/LDAP/SMTP.
- Impostare sempre `DEBUG=0` in produzione.

## Nota su override da Admin

Alcune variabili possono essere sovrascritte dalla Pagina di Amministrazione in `Strumenti -> Impostazioni applicazione`.
Se valorizzate in pagina admin, prevalgono sui valori `.env` per:
- `AGILE_DATE_DISPLAY_FORMAT`
- `AGILE_LOGIN_LOGO_URL`
- `AGILE_FAVICON_URL`
- `AGILE_COMPANY_NAME`
- `AGILE_COPYRIGHT_YEAR`
- `DEFAULT_FROM_EMAIL`
- `AGILE_EMAIL_FROM_NAME`
