# Comandi amministrativi

Questa guida non vuole solo elencare i comandi `manage.py`, ma spiegare **quando usarli**, **per quale problema** e **quale sia il comando giusto da lanciare**.

Uso generale:

```bash
python manage.py <comando> [opzioni]
```

## Mappa rapida

Se il problema e...

- `devo importare o riallineare utenti da LDAP`
  - guarda `import_ldap_users`, `sync_ldap_users`, `check_ldap_user_presence`
- `devo inviare email operative`
  - guarda `send_submission_reminders`, `send_manager_monthly_summary`
- `devo gestire le festivita`
  - guarda `sync_holidays`, `prepare_next_year_holidays`
- `devo migrare dati da una vecchia installazione`
  - guarda `export_release_data`, `import_release_data`
- `devo alleggerire il DB dai log`
  - guarda `purge_audit_logs`

## LDAP

### `import_ldap_users`

**Quando si usa**

- primo popolamento utenti da LDAP
- import massivo iniziale
- situazioni in cui vuoi leggere la directory e creare/aggiornare utenti locali gestiti via LDAP

**Cosa fa**

- crea o aggiorna utenti locali con password non utilizzabile
- imposta `is_active=False` sugli utenti importati
- importa solo anagrafica base LDAP (`username`, nome, cognome, email)

**Quando NON usarlo**

- se gli utenti esistono gia e vuoi solo riallineare nome, cognome o email
  - in quel caso usa `sync_ldap_users`
- se vuoi impostare `Afferenza territoriale`, referente o flag applicativi
  - questi valori vanno gestiti nell'applicazione, non derivati da LDAP

**Esempi**

```bash
python manage.py import_ldap_users
python manage.py import_ldap_users --dry-run
python manage.py import_ldap_users --base-dn "ou=people,dc=example,dc=org" --filter "(objectClass=person)"
```

### `sync_ldap_users`

**Quando si usa**

- gli utenti LDAP esistono gia in locale
- vuoi riallineare i dati anagrafici dalla directory

**Cosa aggiorna**

- `first_name`
- `last_name`
- `email`

**Cosa NON aggiorna**

- `Afferenza territoriale`
- `Responsabile approvazione`
- `Sottoscrizione AILA`
- `Ruolo`
- `Auto-approvazione`

**Quando preferirlo**

- dopo un import iniziale
- quando LDAP e la fonte autorevole per anagrafica e indirizzi email

**Esempi**

```bash
python manage.py sync_ldap_users
python manage.py sync_ldap_users --dry-run
python manage.py sync_ldap_users --deactivate-missing
python manage.py sync_ldap_users --create-missing
```

### `check_ldap_user_presence`

**Quando si usa**

- controllo periodico della coerenza tra utenti locali e directory LDAP

**Cosa fa**

- verifica se gli utenti locali gestiti via LDAP esistono ancora nella directory
- se un utente non esiste piu:
  - imposta `is_active=False`
  - scrive un audit log
  - invia una email riepilogativa ai superuser

**Esempi**

```bash
python manage.py check_ldap_user_presence
python manage.py check_ldap_user_presence --dry-run
```

## Email operative

### `send_submission_reminders`

**Quando si usa**

- per ricordare agli utenti di inviare in approvazione il piano del mese successivo
- come job schedulato o come invio manuale controllato

**Cosa fa**

- scorre gli utenti eleggibili
- salta chi ha gia un piano `SUBMITTED` o `APPROVED`
- evita doppi invii usando un audit log tecnico per lo stesso `anno/mese`

**Quando fare attenzione**

- se forzi il comando (`--force`) puoi reinviare promemoria che normalmente verrebbero saltati

**Esempi**

```bash
python manage.py send_submission_reminders
python manage.py send_submission_reminders --dry-run
python manage.py send_submission_reminders --force
python manage.py send_submission_reminders --date 2026-03-30 --dry-run
```

### `send_manager_monthly_summary`

**Quando si usa**

- per inviare ai responsabili approvazione il riepilogo mensile

**Cosa contiene**

- piani in attesa
- piani approvati
- utenti senza piano
- utenti in auto-approvazione

**Cosa fa internamente**

- evita doppi invii per lo stesso `anno/mese` usando un audit log tecnico

**Esempi**

```bash
python manage.py send_manager_monthly_summary
python manage.py send_manager_monthly_summary --dry-run
python manage.py send_manager_monthly_summary --force
python manage.py send_manager_monthly_summary --date 2026-04-01 --dry-run
```

## Audit log

### `purge_audit_logs`

**Quando si usa**

- per evitare crescita inutile della tabella `AuditLog`
- come manutenzione periodica del database

**Policy consigliata**

- `90 giorni`

**Nota**

- alcuni job usano gli audit log per evitare doppie esecuzioni
- con una retention di `90 giorni` questo e accettabile: al peggio alcuni job annuali innocui possono essere rieseguiti manualmente o automaticamente piu di una volta

**Esempi**

```bash
python manage.py purge_audit_logs --dry-run
python manage.py purge_audit_logs --days 90
python manage.py purge_audit_logs --days 120 --dry-run
```

## Festivita

### `sync_holidays`

**Quando si usa**

- vuoi caricare o correggere un anno specifico
- vuoi un comando diretto e manuale

**Cosa fa**

- carica o aggiorna le festivita nazionali italiane per l'anno indicato

**Quando preferirlo**

- inizializzazione manuale di un anno
- correzione di un anno specifico
- manutenzione puntuale

**Esempi**

```bash
python manage.py sync_holidays --year 2026
python manage.py sync_holidays --year 2026 --overwrite
```

### `prepare_next_year_holidays`

**Quando si usa**

- procedura annuale di preparazione dell'anno successivo

**Cosa fa**

- prepara le festivita del nuovo anno
- copia anche le festivita per sede dall'anno precedente
- invia un report ai superuser
- scrive un audit log per segnare l'esecuzione

**Differenza rispetto a `sync_holidays`**

- `sync_holidays` e un comando manuale su un anno scelto
- `prepare_next_year_holidays` e una procedura annuale piu completa, pensata per il passaggio di anno

**Esempi**

```bash
python manage.py prepare_next_year_holidays --dry-run
python manage.py prepare_next_year_holidays --force --year 2027
```

## Import/Export release

### `export_release_data`

**Quando si usa**

- per esportare dati di configurazione da una installazione esistente
- per preparare una nuova installazione o una migrazione tra ambienti

**Contenuti esportati**

- utenti
- gruppi
- policy afferenze territoriali
- festivita
- template email di sistema
- impostazioni applicazione

**Esempio**

```bash
python manage.py export_release_data ./release-export.json
```

### `import_release_data`

**Quando si usa**

- per importare il JSON di release in una nuova installazione
- per riallineare configurazioni in una istanza gia esistente

**Modalita**

- `merge`
  - upsert senza cancellazioni
- `replace`
  - sostituisce dataset di configurazione senza cancellare gli utenti

**Quando scegliere `merge`**

- vuoi aggiungere o riallineare senza toccare troppo l'esistente

**Quando scegliere `replace`**

- vuoi che policy, festivita, template e impostazioni applicazione riflettano il file importato

**Esempi**

```bash
python manage.py import_release_data ./release-export.json --dry-run
python manage.py import_release_data ./release-export.json --mode merge
python manage.py import_release_data ./release-export.json --mode replace
```
