# Porting performance UI verso versione advanced

Questo documento riassume le ottimizzazioni applicate nel fork Ubuntu 20 per ridurre la lentezza percepita nelle pagine:
- `Quadro generale`
- `Richieste approvazione`
- `Richieste variazioni`
- apertura `Dettaglio`

Obiettivo:
- ridurre query inutili lato backend
- ridurre roundtrip API inutili lato frontend
- mantenere invariato il comportamento funzionale

## Stato di riferimento

Branch fork:
- `codex/ubuntu20-regression`

Commit di riferimento:
- `ea23217` `Reduce admin queue and overview latency`

File sorgente principali:
- [`agile/views.py`](/Users/master/Documents/projects/lagile.new/agile_work_ubuntu20/agile/views.py)
- [`agile/serializers.py`](/Users/master/Documents/projects/lagile.new/agile_work_ubuntu20/agile/serializers.py)
- [`templates/employee_app.html`](/Users/master/Documents/projects/lagile.new/agile_work_ubuntu20/templates/employee_app.html)

## Problemi individuati

### 1. Overview admin troppo costosa

In `AdminOverviewView` il fork caricava tutti i `PlanDay` del mese con `prefetch_related('days')` e poi contava in Python:
- giorni `REMOTE`
- giorni `ON_SITE`

Questo diventava costoso al crescere di utenti e piani.

In piu, la view caricava gli utenti con `only(...)` ma senza `auto_approve`, e poi leggeva `user.auto_approve` durante la costruzione righe:
- risultato: query aggiuntive per utente

### 2. Serializer piano con query extra

`MonthlyPlanSerializer` calcolava:
- `has_pending_change_request`
- `latest_change_request_status`
- `latest_change_request_response_reason`

leggendo ogni volta `obj.change_requests...`, quindi con ulteriori query per piano.

### 3. Frontend dettaglio troppo verboso

Nel template:
- il click su `Dettaglio` nelle approvazioni ricaricava `/plans/` completo
- il click su `Dettaglio` nelle variazioni ricaricava `/change-requests/` completo e poi `/plans/` completo
- il click su `Dettaglio` nell'overview ricaricava `/plans/` completo

Per aprire un solo dettaglio si scaricavano liste intere.

## Ottimizzazioni applicate

### Backend: overview con aggregazioni SQL

In `AdminOverviewView`:
- rimosso `prefetch_related('days')`
- aggiunte annotazioni:
  - `remote_days_count=Count('days', filter=Q(days__work_type='REMOTE'))`
  - `on_site_days_count=Count('days', filter=Q(days__work_type='ON_SITE'))`

I contatori vengono quindi letti direttamente dal DB.

Inoltre, il queryset utenti ora include anche:
- `auto_approve`

per evitare caricamenti lazy campo-per-campo.

### Backend: annotazioni sul queryset piani

In `MonthlyPlanViewSet.get_queryset()`:
- `has_pending_change_request_db` via `Exists(...)`
- `latest_change_request_status_db` via `Subquery(...)`
- `latest_change_request_response_reason_db` via `Subquery(...)`

Il serializer usa queste annotazioni quando presenti, evitando query aggiuntive su `change_requests`.

### Frontend: dettaglio con cache locale e retrieve singola

Nel template `employee_app.html`:
- introdotte mappe locali:
  - `approverPlanById`
  - `changeRequestById`
- quando la coda approvazioni o variazioni viene renderizzata, gli oggetti sono indicizzati per `id`
- all'apertura del dettaglio:
  - si usa prima l'oggetto gia in memoria
  - se manca, si usa `GET /plans/{id}/` oppure `GET /change-requests/{id}/`
  - non si scaricano piu liste complete

## Checklist di porting verso advanced

Applicare in quest'ordine:

1. Identificare la view equivalente di `AdminOverviewView`.
2. Sostituire conteggi Python su `days` con annotazioni `Count(..., filter=...)`.
3. Verificare eventuali `only(...)` che escludono campi poi letti nel loop.
4. Identificare il queryset equivalente di `MonthlyPlanViewSet`.
5. Annotare:
   - pending change request
   - ultimo stato change request
   - ultima response reason
6. Aggiornare il serializer per usare le annotazioni quando presenti.
7. Nel frontend, evitare `GET` di collezioni intere quando serve un singolo dettaglio.
8. Mantenere una cache locale `id -> oggetto` per righe gia renderizzate.
9. Dove manca l'oggetto, fare una retrieve singola `/{id}/`.

## Punti da cercare nella versione advanced

Backend:
- view overview admin
- queryset piani admin/approvatore
- serializer piano con campi derivati da `change_requests`

Frontend:
- handler click pulsante `Dettaglio`
- chiamate a `/plans/`
- chiamate a `/change-requests/`
- eventuali dropdown o tabelle che hanno gia i dati necessari in memoria

## Regola pratica da mantenere

Se l'interfaccia deve aprire il dettaglio di un solo elemento:
- usare il record gia caricato in pagina, se disponibile
- altrimenti chiamare l'endpoint singolo `/{id}/`
- evitare di ricaricare l'intera collezione solo per fare una `find(...)`

## Verifica consigliata dopo il porting

Misurare almeno questi casi:
- apertura `Quadro generale`
- apertura `Richieste approvazione`
- apertura `Richieste variazioni`
- click su `Dettaglio`

Se resta lenta:
- confrontare numero query backend
- verificare payload JSON delle liste
- verificare se il collo di bottiglia e rendering DOM o fetch API
