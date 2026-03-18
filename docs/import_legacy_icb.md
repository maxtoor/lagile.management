# Import legacy ICB

Questa guida descrive esclusivamente l'importazione dei dati storici della versione precedente per ICB.

## File necessari

Per il flusso completo servono:

- `ICB_backup.csv`
  - backup CSV completo usato per utenti, sedi operative, referenti e storico `Programmazione`
- `ICB_leaves_report_between_2025_01_01_and_2026_12_31.csv`
  - leaves report legacy usato per stati e note/attivita

## Comandi principali

### `import_icb_legacy_bundle`

Procedura unica per:
- aggiornare o creare utenti dal backup CSV
- applicare sede operativa e referente
- importare anche i gruppi utenti dal campo `Gruppo` del CSV
- importare lo storico `Programmazione` in `MonthlyPlan` e `PlanDay`
- opzionalmente riallineare nome, cognome ed email da LDAP

Esempio:

```bash
python manage.py import_icb_legacy_bundle ./import/ICB_backup.csv \
  --with-ldap-sync \
  --overwrite-existing-plans \
  --leaves-report-csv ./import/ICB_leaves_report_between_2025_01_01_and_2026_12_31.csv
```

Opzioni rilevanti:
- `--dry-run`: simula senza scrivere modifiche
- `--with-ldap-sync`: riallinea `first_name`, `last_name`, `email` da LDAP dopo il sync utenti
- `--overwrite-existing-plans`: riscrive i piani gia presenti nel range storico
- `--skip-user-sync`: salta la fase utenti/referenti
- `--leaves-report-csv`: usa il leaves report per importare correttamente stato mese corrente/prossimo

### `import_legacy_icb_notes`

Importa le descrizioni attivita dal `Leaves report` legacy e le copia in `PlanDay.notes`.

Esempio:

```bash
python manage.py import_legacy_icb_notes ./import/ICB_leaves_report_between_2025_01_01_and_2026_12_31.csv \
  --backup-csv-path ./import/ICB_backup.csv
```

Opzioni rilevanti:
- `--dry-run`: simula l'import note
- `--backup-csv-path`: usa il backup CSV come mappa di riconciliazione aggiuntiva nome/email

### `import_legacy_icb_backup`

Comando piu basso livello, normalmente non necessario se usi il bundle.

Importa solo lo storico `Programmazione` dal backup CSV in `MonthlyPlan` / `PlanDay`.

Esempio:

```bash
python manage.py import_legacy_icb_backup ./import/ICB_backup.csv --dry-run
```

## Ordine consigliato

1. Deploy applicazione
2. `migrate`
3. `createsuperuser`
4. `import_icb_legacy_bundle`
5. `import_legacy_icb_notes`

## Dry-run consigliato

Prima dell'import reale:

```bash
python manage.py import_icb_legacy_bundle ./import/ICB_backup.csv \
  --with-ldap-sync \
  --overwrite-existing-plans \
  --leaves-report-csv ./import/ICB_leaves_report_between_2025_01_01_and_2026_12_31.csv \
  --dry-run

python manage.py import_legacy_icb_notes ./import/ICB_leaves_report_between_2025_01_01_and_2026_12_31.csv \
  --backup-csv-path ./import/ICB_backup.csv \
  --dry-run
```

## URL utili nella vecchia applicazione

Backup CSV completo:
- `Settings -> General -> Download backup`
- route legacy: `/settings/company/backup/`

Leaves report CSV:
- `Reports -> Leaves`
- export CSV via route:

```text
/reports/leaves/?as-csv=1&start_date=2025-01-01&end_date=2026-12-31
```

## Note pratiche

- `ICB_backup.csv` resta la sorgente principale per utenti, sedi operative e storico giorni
- la colonna `Gruppo` del backup viene usata sia per derivare la sede operativa sia per assegnare i gruppi Django
- il `Leaves report` completa stati e descrizioni attivita
- il bundle usa un matching utenti prudente:
  - match email
  - match username derivato dall'email
  - evita fallback deboli che possono assegnare dati alla persona sbagliata
