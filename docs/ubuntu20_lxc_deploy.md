# Deploy Ubuntu 20 in container LXC senza Docker

Questa guida descrive il deploy da zero della branch `release/ubuntu20-regression` in un container LXC con Ubuntu 20, in un contesto dove Docker non puo essere avviato.

## Scopo della branch

`release/ubuntu20-regression` e una branch operativa dedicata a questo scenario specifico:

- container LXC o host con Ubuntu 20
- deploy nativo senza Docker
- esigenza di mantenere il servizio attivo in modo transitorio e controllato

Questa branch non sostituisce la linea standard del progetto:

- `main` resta la linea normale per il deploy Docker
- `release/ubuntu20-regression` resta una branch di deploy nativo per ambienti vincolati

## Prerequisiti

Pacchetti di base consigliati:

```bash
apt update
apt install -y git python3 python3-venv python3-pip postgresql postgresql-contrib
```

Se usi `gunicorn` via `systemd`, assicurati di avere anche:

```bash
apt install -y nginx
```

`nginx` non e obbligatorio se esponi direttamente `gunicorn`, ma in installazioni stabili resta consigliabile.

## Directory applicativa

Esempio di directory usata in questa documentazione:

```bash
mkdir -p /opt/containers
cd /opt/containers
git clone https://github.com/maxtoor/lagile.management.git lagile-management
cd /opt/containers/lagile-management
git checkout release/ubuntu20-regression
```

Atteso:

```bash
root@timeoff:/opt/containers/lagile-management#
```

## PostgreSQL: requisito fondamentale UTF8

Il database deve essere in `UTF8`.

Questo punto e importante:

- un cluster o database in `SQL_ASCII` rompe gli import legacy con testi accentati e campi JSON
- su Ubuntu 20 minimale puo non esistere `it_IT.UTF-8`
- in quel caso `C.UTF-8` e un fallback valido

Controllo rapido del cluster:

```bash
sudo -u postgres psql -c "\\l"
```

Se vedi database o template in `SQL_ASCII`, e meglio ricreare il cluster prima di procedere.

### Ricreazione cluster PostgreSQL in UTF8

Se il container e nuovo e il database e ancora vuoto, la strada piu pulita e:

```bash
systemctl stop postgresql
pg_dropcluster --stop 12 main
pg_createcluster --locale C.UTF-8 --encoding UTF8 12 main
systemctl start postgresql
pg_lsclusters
sudo -u postgres psql -c "\\l"
```

Atteso:

- cluster `12/main` attivo
- encoding `UTF8`
- locale `C.UTF-8` oppure altra locale UTF8 valida

### Creazione utente e database applicativo

Apri `psql` come utente `postgres`:

```bash
sudo -u postgres psql
```

Poi esegui:

```sql
CREATE USER agile WITH PASSWORD 'agile';
CREATE DATABASE agile_work OWNER agile ENCODING 'UTF8' TEMPLATE template0;
GRANT ALL PRIVILEGES ON DATABASE agile_work TO agile;
\q
```

Verifica finale:

```bash
sudo -u postgres psql -d agile_work -c "SHOW server_encoding;"
```

Atteso:

```text
UTF8
```

## Virtualenv Python

Dentro la directory applicativa:

```bash
cd /opt/containers/lagile-management
python3 -m venv .venv
source .venv/bin/activate
```

Atteso:

```bash
(.venv) root@timeoff:/opt/containers/lagile-management#
```

Aggiorna `pip` e installa le dipendenze:

```bash
(.venv) pip install --upgrade pip
(.venv) pip install -r requirements.txt
```

## File `.env`

Copia il file di esempio:

```bash
(.venv) cp .env.example .env
```

Impostazioni minime consigliate per deploy nativo Ubuntu 20:

```env
DJANGO_SECRET_KEY=una-chiave-forte
DEBUG=0
ALLOWED_HOSTS=localhost,127.0.0.1,timeoff
TIME_ZONE=Europe/Rome

POSTGRES_DB=agile_work
POSTGRES_USER=agile
POSTGRES_PASSWORD=agile
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432

AGILE_PUBLIC_BASE_URL=http://timeoff:8000

AGILE_LOG_FILE=/opt/containers/lagile-management/logs/agile.log
AGILE_LOG_MONITOR_FILE=/opt/containers/lagile-management/logs/agile.log
AGILE_LOG_MONITOR_SOURCES=app:/opt/containers/lagile-management/logs/agile.log;scheduler:/opt/containers/lagile-management/logs/scheduler.log
```

Se serve SMTP o LDAP, completa il resto delle variabili secondo la tua installazione.

## Migrazioni e superuser

Sempre con virtualenv attivo:

```bash
(.venv) python manage.py migrate
(.venv) python manage.py createsuperuser
(.venv) python manage.py check
(.venv) python manage.py collectstatic --noinput
```

Se tutto e corretto, `check` deve rispondere senza errori.

## Test applicativi minimi

Esempi utili prima di collegare `systemd`:

```bash
(.venv) python manage.py showmigrations
(.venv) python manage.py send_submission_reminders --dry-run
(.venv) python manage.py send_manager_monthly_summary --dry-run
(.venv) python manage.py prepare_next_year_holidays --dry-run
(.venv) python manage.py check_ldap_user_presence --dry-run
```

## Avvio con gunicorn

Test manuale rapido:

```bash
(.venv) gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

Se il processo parte correttamente, interrompi con `Ctrl+C` e passa a `systemd`.

## Esempio unit file systemd

File:

```text
/etc/systemd/system/lagile-web.service
```

Contenuto di esempio:

```ini
[Unit]
Description=LAgile Management Gunicorn
After=network.target postgresql.service

[Service]
User=root
Group=root
WorkingDirectory=/opt/containers/lagile-management
EnvironmentFile=/opt/containers/lagile-management/.env
ExecStart=/opt/containers/lagile-management/.venv/bin/gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Attivazione:

```bash
systemctl daemon-reload
systemctl enable lagile-web
systemctl restart lagile-web
systemctl status lagile-web
```

## Aggiornamento applicativo

Flusso consigliato:

```bash
cd /opt/containers/lagile-management
git checkout release/ubuntu20-regression
git pull --no-rebase origin release/ubuntu20-regression
source .venv/bin/activate
python manage.py check
python manage.py collectstatic --noinput
systemctl restart lagile-web
systemctl status lagile-web
```

## Logging nativo

Verifica rapida:

```bash
ls -la /opt/containers/lagile-management/logs
tail -n 50 /opt/containers/lagile-management/logs/agile.log
tail -n 50 /opt/containers/lagile-management/logs/scheduler.log
```

Se i file non esistono ancora, controlla le variabili `AGILE_LOG_*` nel `.env`.

## Scheduler e job periodici

In un deploy senza Docker non esiste il servizio `scheduler` del `docker compose`.

Le strade tipiche sono:

- usare `cron`
- lanciare manualmente i comandi operativi quando necessario

Esempi di comandi:

```bash
(.venv) python manage.py send_submission_reminders --dry-run
(.venv) python manage.py send_manager_monthly_summary --dry-run
(.venv) python manage.py prepare_next_year_holidays --dry-run
(.venv) python manage.py check_ldap_user_presence --dry-run
```

## Import legacy

In questa branch gli import legacy sono stati adattati e verificati anche in ambiente Ubuntu 20.

Riferimento:

- [`docs/import_legacy_icb.md`](/Users/master/Documents/projects/lagile.new/agile_work/docs/import_legacy_icb.md)

Punto importante:

- il database deve essere `UTF8`
- per gli import reali conviene usare `--overwrite-existing-plans` se stai rigenerando mesi gia presenti

## Stato atteso della branch

`release/ubuntu20-regression` va considerata una branch di esercizio transitorio e controllato:

- adatta a mantenere il servizio operativo in un container LXC Ubuntu 20
- studiata per ambienti dove Docker non puo essere avviato
- utile come soluzione pragmatica in attesa di una piattaforma piu moderna
- non destinata a sostituire la linea standard Docker del progetto
