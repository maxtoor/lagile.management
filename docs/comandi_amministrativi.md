# Comandi amministrativi

Questa guida raccoglie i principali comandi `manage.py` usati per manutenzione, sincronizzazione e operazioni straordinarie.

Uso generale:

```bash
python manage.py <comando> [opzioni]
```

## LDAP

### `import_ldap_users`

Importa nel database locale utenti letti da LDAP.

Caratteristiche:
- crea o aggiorna utenti locali con password non utilizzabile
- imposta `is_active=False` sugli utenti importati
- valorizza `Afferenza territoriale` solo se il valore LDAP e tra quelli ammessi da `AGILE_SITES`

Esempi:

```bash
python manage.py import_ldap_users
python manage.py import_ldap_users --dry-run
python manage.py import_ldap_users --base-dn "ou=people,dc=example,dc=org" --filter "(objectClass=person)"
```

### `sync_ldap_users`

Allinea gli utenti LDAP gia presenti in locale.

Aggiorna:
- `first_name`
- `last_name`
- `email`

Non aggiorna:
- `Afferenza territoriale`
- `Responsabile approvazione`
- `Sottoscrizione AILA`
- `Ruolo`
- `Auto-approvazione`

Esempi:

```bash
python manage.py sync_ldap_users
python manage.py sync_ldap_users --dry-run
python manage.py sync_ldap_users --deactivate-missing
python manage.py sync_ldap_users --create-missing
```

### `check_ldap_user_presence`

Verifica se gli utenti locali gestiti via LDAP esistono ancora nella directory.

Se un utente non esiste piu:
- viene impostato `is_active=False`
- viene scritto un audit log
- viene inviata una email riepilogativa ai superuser

Esempi:

```bash
python manage.py check_ldap_user_presence
python manage.py check_ldap_user_presence --dry-run
```

## Email operative

### `send_submission_reminders`

Invia promemoria agli utenti che non hanno ancora inviato in approvazione il piano del mese successivo.

Esempi:

```bash
python manage.py send_submission_reminders
python manage.py send_submission_reminders --dry-run
python manage.py send_submission_reminders --force
python manage.py send_submission_reminders --date 2026-03-30 --dry-run
```

### `send_manager_monthly_summary`

Invia ai responsabili approvazione il riepilogo del mese:
- piani in attesa
- piani approvati
- utenti senza piano
- utenti in auto-approvazione

Esempi:

```bash
python manage.py send_manager_monthly_summary
python manage.py send_manager_monthly_summary --dry-run
python manage.py send_manager_monthly_summary --force
python manage.py send_manager_monthly_summary --date 2026-04-01 --dry-run
```

## Festivita

### `sync_holidays`

Carica o aggiorna le festivita nazionali italiane per un anno specifico.

Esempi:

```bash
python manage.py sync_holidays --year 2026
python manage.py sync_holidays --year 2026 --overwrite
```

### `prepare_next_year_holidays`

Predispone le festivita dell'anno successivo e invia un report ai superuser.

Esempi:

```bash
python manage.py prepare_next_year_holidays --dry-run
python manage.py prepare_next_year_holidays --force --year 2027
```

## Import/Export release

### `export_release_data`

Esporta configurazione e anagrafica base in JSON.

Contenuti esportati:
- utenti
- gruppi
- policy afferenze territoriali
- festivita
- template email di sistema
- impostazioni applicazione

Esempio:

```bash
python manage.py export_release_data ./release-export.json
```

### `import_release_data`

Importa il JSON di release in una nuova installazione o in un'istanza esistente.

Modalita:
- `merge`: upsert senza cancellazioni
- `replace`: sostituisce dataset di configurazione senza cancellare gli utenti

Esempi:

```bash
python manage.py import_release_data ./release-export.json --dry-run
python manage.py import_release_data ./release-export.json --mode merge
python manage.py import_release_data ./release-export.json --mode replace
```
