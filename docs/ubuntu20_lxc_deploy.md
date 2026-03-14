# Deploy Ubuntu 20 in container LXC senza Docker

Questo documento chiarisce il contesto della branch `release/ubuntu20-regression`.

## Scopo della branch

La branch `release/ubuntu20-regression` non nasce come variante generica di prodotto, ma come linea di deploy studiata per un contesto operativo specifico:

- host o container LXC con Ubuntu 20
- impossibilita pratica o politica di avviare Docker dentro l'ambiente target
- esigenza di mantenere l'applicazione attiva in modo transitorio, in attesa di una macchina o di uno stack piu aggiornato

In questo scenario la branch viene eseguita in modo nativo, tipicamente con:

- virtualenv Python locale
- PostgreSQL locale
- `gunicorn` gestito da `systemd`
- statici raccolti con `collectstatic`
- job periodici eseguiti via `cron` o comandi amministrativi espliciti

## Posizionamento rispetto a `main`

Regola pratica:

- `main` resta la linea standard del progetto, pensata prima di tutto per il deploy Docker
- `release/ubuntu20-regression` resta una branch dedicata al deploy nativo in ambiente Ubuntu 20 / LXC senza Docker

Questa branch non va letta come nuova baseline architetturale del progetto, ma come adattamento operativo per un vincolo infrastrutturale reale.

## Quando usarla

Usare `release/ubuntu20-regression` solo se valgono insieme queste condizioni:

- il target e Ubuntu 20
- il deploy Docker non e disponibile o non e autorizzato
- serve mantenere in esercizio l'applicazione in modo pragmatico e controllato

Se Docker e disponibile, il percorso consigliato resta `main`.

## Flusso sintetico di deploy

Esempio di allineamento codice su server:

```bash
cd /opt/containers/lagile-management
git checkout release/ubuntu20-regression
git pull --no-rebase origin release/ubuntu20-regression
```

Esempio di aggiornamento applicativo:

```bash
source .venv/bin/activate
python manage.py check
python manage.py collectstatic --noinput
systemctl restart lagile-web
systemctl status lagile-web
```

## Note operative da ricordare

- il database PostgreSQL deve essere in `UTF8`
- in installazioni minimali Ubuntu 20 puo essere necessario usare locale `C.UTF-8`
- i path log vanno pensati in forma nativa, non Docker
- alcune correzioni presenti in questa branch nascono da esigenze specifiche del deploy nativo Ubuntu 20

## Stato atteso della branch

`release/ubuntu20-regression` va considerata una branch di esercizio transitorio e controllato:

- adatta a tenere operativo il servizio
- documentata per il contesto LXC/Ubuntu 20
- non destinata a sostituire la linea standard Docker del progetto
