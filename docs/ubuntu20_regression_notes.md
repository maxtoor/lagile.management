## Ubuntu 20 regression guide

Questa linea di lavoro serve a verificare se l'app puo girare in modo transitorio su:
- Ubuntu `20.04`
- Python `3.8`
- PostgreSQL `12`
- installazione nativa, senza Docker

L'obiettivo non e creare una nuova linea di prodotto, ma isolare un setup ponte senza sporcare `main`.

## Stato attuale della branch

Differenze principali rispetto a `main`:
- `Django==4.2.29`
- `django-auth-ldap==5.0.0`
- `whitenoise==6.7.0`
- riduzione della sintassi Python `3.10+` piu evidente
- caricamento interno di `.env` da [`config/settings.py`](/Users/master/Documents/projects/lagile.new/agile_work/config/settings.py)
- static serviti con WhiteNoise

Commit rilevanti:
- `d7f8df1` `Load .env directly in Ubuntu 20 fork`
- `c3aff6a` `Serve static files in Ubuntu 20 fork`
- `5f8cd46` `Pin WhiteNoise to 6.7.0 for Python 3.8`

## Cosa e stato verificato

Sul target reale Ubuntu 20 sono gia stati verificati questi punti:
- `python3 --version` -> `3.8.10`
- `psql --version` -> PostgreSQL `12.22`
- `python -m pip install -r requirements.txt` riuscito
- `python manage.py migrate` riuscito
- `python manage.py createsuperuser` riuscito
- `python manage.py runserver 0.0.0.0:8000` riuscito
- `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3` riuscito
- `python manage.py collectstatic --noinput` riuscito
- servizio `systemd` `lagile-web` riuscito
- scheduler via `cron` riuscito

Restano da rifinire alcuni dettagli UI dell'admin, ma il nucleo applicativo gira.

## Feature integrate nella release Ubuntu 20

Ad oggi `release/ubuntu20-regression` include anche il `Calendario condiviso`.

Caratteristiche operative della vista:
- accessibile a tutti gli utenti autenticati
- basata solo su piani `APPROVED`
- nessun dettaglio apribile cliccando il nome del collega
- evidenza principale sulle giornate `LA`
- weekend e festivita con lo stesso sfondo tenue
- colleghi senza piano approvato mostrati con nome attenuato

La vista e stata verificata anche nel contesto reale Ubuntu 20 come estensione compatibile della shell transitoria.

## Installazione da zero su Ubuntu 20

### 1. Clona il repository principale e usa la branch release

```bash
mkdir -p /opt/containers
git clone https://github.com/maxtoor/lagile.management.git /opt/containers/lagile-management
cd /opt/containers/lagile-management
git checkout release/ubuntu20-regression
```

### 2. Installa i pacchetti di sistema

```bash
apt update
apt install -y \
  git python3 python3-venv python3-pip \
  build-essential libpq-dev libldap2-dev libsasl2-dev libssl-dev \
  postgresql postgresql-client postgresql-contrib
```

### 3. Verifica Python e PostgreSQL

```bash
python3 --version
psql --version
pg_lsclusters
```

Atteso:
- Python `3.8.x`
- PostgreSQL `12.x`
- cluster `12 main` online su `5432`
- cluster/template in `UTF8` e non in `SQL_ASCII`

Se il cluster non e online:

```bash
pg_ctlcluster 12 main start
pg_lsclusters
```

Verifica encoding cluster/template:

```bash
sudo -u postgres psql -c "\l"
```

Atteso:
- `postgres`, `template0`, `template1` in `UTF8`

Se il cluster e stato inizializzato in `SQL_ASCII`, ricrearlo prima di procedere.

Esempio rapido se il cluster e ancora vuoto:

```bash
systemctl stop postgresql
pg_dropcluster --stop 12 main
pg_createcluster --locale it_IT.UTF-8 --encoding UTF8 12 main
systemctl start postgresql
pg_lsclusters
sudo -u postgres psql -c "\l"
```

Nota:
- su installazioni Ubuntu minimali `it_IT.UTF-8` potrebbe non essere disponibile
- in quel caso usare `C.UTF-8`, che e sufficiente per avere un cluster/database in `UTF8`

Esempio compatibile:

```bash
systemctl stop postgresql
pg_dropcluster --stop 12 main
pg_createcluster --locale C.UTF-8 --encoding UTF8 12 main
systemctl start postgresql
pg_lsclusters
sudo -u postgres psql -c "\l"
```

### 4. Crea database e utente

```bash
sudo -u postgres psql
```

Poi:

```sql
CREATE USER agile WITH PASSWORD 'agile';
CREATE DATABASE agile_work OWNER agile ENCODING 'UTF8' TEMPLATE template0;
GRANT ALL PRIVILEGES ON DATABASE agile_work TO agile;
\q
```

### 5. Crea virtualenv e installa i requirements

```bash
cd /opt/containers/lagile-management
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 6. Crea `.env`

```bash
cp .env.example .env
```

Configurazione minima consigliata:

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

AGILE_SITES=Napoli
AGILE_PUBLIC_BASE_URL=http://127.0.0.1:8000

LDAP_ENABLED=0
```

Nota importante:
- in questo fork `settings.py` legge `.env` direttamente
- non serve `source .env`
- anzi, conviene evitare di esportare manualmente variabili `POSTGRES_*`, perche possono sporcare la shell
- `.env.example` e ora orientato prima all'installazione nativa Ubuntu 20
- i path log corretti per installazione nativa sono sotto `/opt/containers/lagile-management/logs/`
- se nel `.env` erano rimasti vecchi path Docker `/app/logs/...`, il fork li normalizza automaticamente verso la directory `logs/` del progetto

### 7. Inizializza Django

```bash
cd /opt/containers/lagile-management
source .venv/bin/activate
python manage.py migrate
python manage.py createsuperuser
python manage.py check
python manage.py collectstatic --noinput
```

### 8. Avvio rapido

```bash
python manage.py runserver 0.0.0.0:8000
```

### 9. Avvio con gunicorn

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

### 10. Servizio systemd per gunicorn

Crea:

- [`/etc/systemd/system/lagile-web.service`](/etc/systemd/system/lagile-web.service)

```ini
[Unit]
Description=LAgile Management Gunicorn
After=network.target postgresql.service

[Service]
User=root
WorkingDirectory=/opt/containers/lagile-management
Environment="PATH=/opt/containers/lagile-management/.venv/bin"
ExecStart=/opt/containers/lagile-management/.venv/bin/gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
Restart=always

[Install]
WantedBy=multi-user.target
```

Poi:

```bash
systemctl daemon-reload
systemctl enable --now lagile-web
systemctl status lagile-web
```

Controllo porta:

```bash
ss -lntp | grep 8000
```

### 11. Scheduler con cron

Crea:

- [`/etc/cron.d/lagile-management`](/etc/cron.d/lagile-management)

```cron
0 * * * * root cd /opt/containers/lagile-management && ./.venv/bin/python manage.py send_submission_reminders >> logs/scheduler.log 2>&1
5 * * * * root cd /opt/containers/lagile-management && ./.venv/bin/python manage.py send_manager_monthly_summary >> logs/scheduler.log 2>&1
10 * * * * root cd /opt/containers/lagile-management && ./.venv/bin/python manage.py prepare_next_year_holidays >> logs/scheduler.log 2>&1
15 * * * * root cd /opt/containers/lagile-management && ./.venv/bin/python manage.py check_ldap_user_presence >> logs/scheduler.log 2>&1
```

Verifiche:

```bash
cat /etc/cron.d/lagile-management
systemctl status cron
tail -n 50 /opt/containers/lagile-management/logs/scheduler.log
```

Test manuale consigliato di un job:

```bash
cd /opt/containers/lagile-management
source .venv/bin/activate
python manage.py check_ldap_user_presence --dry-run
```

## Problemi incontrati e correzioni

### PostgreSQL in `SQL_ASCII`

Se PostgreSQL viene inizializzato in `SQL_ASCII`, l'app puo sembrare funzionare ma gli import legacy possono fallire su JSON e testi accentati.

Sintomo tipico:

```text
unsupported Unicode escape sequence
... server encoding is not UTF8
```

Controlli rapidi:

```bash
sudo -u postgres psql -d agile_work -c "SHOW server_encoding;"
sudo -u postgres psql -c "\l"
```

Atteso:
- database e template in `UTF8`

Se il cluster e ancora vuoto, conviene ricrearlo direttamente in `UTF8` invece di tentare workaround applicativi.

### `.env` non source-friendly

Nel ramo principale alcune righe del file `.env` si prestano male a `source .env`, per esempio:
- `LDAP_USER_FILTER=(uid=%(user)s)`
- `AGILE_LOG_MONITOR_SOURCES=...;...`

Per questo la branch carica `.env` da Python in [`config/settings.py`](/Users/master/Documents/projects/lagile.new/agile_work/config/settings.py).

### Vecchie variabili `POSTGRES_*` esportate nella shell

Se la shell contiene gia:
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

quelle variabili possono prevalere sul file `.env`.

Controllo rapido:

```bash
env | grep '^POSTGRES_'
```

Se vedi valori vecchi, pulisci la shell:

```bash
unset POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD
```

### Static con gunicorn

Con `gunicorn` puro gli static non vengono serviti correttamente senza supporto aggiuntivo.

Per questo la branch usa:
- `whitenoise==6.7.0`
- `whitenoise.middleware.WhiteNoiseMiddleware`
- `STATIC_ROOT = BASE_DIR / 'staticfiles'`
- `WHITENOISE_USE_FINDERS = True`

Dopo ogni aggiornamento dei file statici:

```bash
cd /opt/containers/lagile-management
source .venv/bin/activate
python manage.py collectstatic --noinput
```

### Versione di WhiteNoise

Su Python `3.8` il pin `whitenoise==6.9.0` non risultava installabile.

La versione verificata e:
- `whitenoise==6.7.0`

## Ordine di verifica consigliato

Quando prepari una nuova istanza Ubuntu 20, l'ordine piu sicuro e:

1. installazione pacchetti di sistema
2. PostgreSQL 12 online
3. creazione DB e utente
4. `python -m pip install -r requirements.txt`
5. creazione `.env`
6. `python manage.py migrate`
7. `python manage.py createsuperuser`
8. `python manage.py check`
9. `python manage.py collectstatic --noinput`
10. prova con `runserver`
11. prova con `gunicorn`
12. attivazione `systemd`
13. attivazione `cron`

## Controlli finali utili

Servizi:

```bash
systemctl status lagile-web
systemctl status cron
pg_lsclusters
```

Porte:

```bash
ss -lntp | grep 8000
ss -lntp | grep 5432
```

Verifiche applicative:
- home del portale
- `/admin/login/`
- login admin
- caricamento CSS/static

## Conclusione

La branch Ubuntu 20 non e solo teorica: nel target reale ha gia dimostrato di reggere almeno questi punti:
- installazione requirements
- migrazioni
- superuser
- `runserver`
- `gunicorn`
- `collectstatic`
- `systemd`
- `cron`

Restano possibili rifiniture UI o operative, ma la base tecnica del deploy transitorio e stata validata.

Senza Docker e senza reverse proxy locale, `gunicorn` non serve da solo gli static. Il fork risolve il problema con:
- `whitenoise.middleware.WhiteNoiseMiddleware`
- `STATIC_ROOT`
- `WHITENOISE_USE_FINDERS = True`

Dopo aggiornamenti lato codice:

```bash
python -m pip install -r requirements.txt
python manage.py collectstatic --noinput
```

## Ordine consigliato di debug se qualcosa fallisce

1. `python -m pip install -r requirements.txt`
2. `python manage.py check`
3. `python manage.py migrate`
4. login admin
5. login portale
6. static con `gunicorn`
7. servizio `lagile-web`
8. cron
9. solo dopo: import legacy ICB

## Dipendenze da tenere d'occhio

Se una nuova macchina Ubuntu 20 mostra errori diversi, i pacchetti da verificare per primi sono:

1. `djangorestframework==3.15.2`
2. `django-auth-ldap==5.0.0`
3. `python-ldap==3.4.4`
4. `psycopg[binary]==3.2.3`
5. `holidays>=0.56,<1.0`

Regola pratica:
- cambiare una dipendenza alla volta
- verificare subito `pip install`
- non toccare logica applicativa finche non emerge un errore concreto

## Stato transitional-ready

Alla data di venerdi 13 marzo 2026 la branch `release/ubuntu20-regression` puo essere considerata pronta per uso transitorio su Ubuntu 20 senza Docker, con i seguenti punti gia verificati sul target reale:

- Python `3.8`
- PostgreSQL `12`
- installazione `requirements`
- `migrate`
- `createsuperuser`
- `python manage.py check`
- `runserver`
- `gunicorn`
- `collectstatic`
- `systemd`
- `cron`
- comandi amministrativi principali in `--dry-run`
- logging nativo su `logs/agile.log` e `logs/scheduler.log`
- UI admin compatibile con Django `4.2` sui blocchi collassabili
- portale utente e admin con palette semplificata e superfici bianche
- ottimizzazioni performance per:
  - `Programmazione`
  - `Quadro generale`
  - `Richieste approvazione`
  - `Richieste variazioni`
  - apertura `Dettaglio`

### Vincoli noti da ricordare

- il cluster PostgreSQL deve essere creato in `UTF8`
- se `it_IT.UTF-8` non e disponibile sulla macchina, usare `C.UTF-8`
- un cluster inizializzato in `SQL_ASCII` non e adatto agli import legacy con testi accentati
- dopo modifiche a static/admin theme, eseguire sempre `collectstatic --noinput`
- i vecchi path Docker `/app/logs/...` sono tollerati dal codice, ma nei deploy nativi e preferibile usare path reali sotto `/opt/containers/lagile-management/logs/`

### Rifiniture opzionali rimaste fuori dal perimetro minimo

- porting delle ottimizzazioni performance nella versione "advanced"
- ulteriore profiling su pagine admin se il dataset cresce molto
- esecuzione completa import legacy ICB su database UTF8 appena inizializzato

Documenti collegati:
- [`performance_porting_advanced.md`](/Users/master/Documents/projects/lagile.new/agile_work/docs/performance_porting_advanced.md)
- [`import_legacy_icb.md`](/Users/master/Documents/projects/lagile.new/agile_work/docs/import_legacy_icb.md)
