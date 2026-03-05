# Migrazione dalla versione precedente (Istituti CNR)

Nota: questa procedura riguarda esclusivamente gli Istituti del CNR che avevano adottato la versione precedente di questo software.

## Flusso consigliato

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

## Aggiornamento sede utenti da CSV (match su email)

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

### Variante ICB (creazione utenti mancanti)

Per l'Istituto di Chimica Biomolecolare (ICB) e disponibile una variante dedicata che, a parita di logica CSV,
crea automaticamente l'utente locale se non viene trovato.

```bash
python manage.py update_user_sites_from_csv_icb /percorso/file.csv --site-column department --site-mode last-word
python manage.py update_user_sites_from_csv_icb /percorso/file.csv --dry-run
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
  - `Sede A (oscurata)` -> referente assegnato (oscurato), `auto_approve=Si`
  - `Sede B (oscurata)` -> referente assegnato (oscurato), `auto_approve=No`
  - `Sede C (oscurata)` -> referente assegnato (oscurato), `auto_approve=No`
  - `Sede D (oscurata)` -> referente assegnato (oscurato), `auto_approve=No`
- se un utente viene usato come referente da queste regole e non e gia `ADMIN`/`SUPERADMIN`, viene impostato a ruolo `Referente Amministrativo` (`ADMIN`)
- il comando stampa un report finale con aggiornati/invariati/non trovati/sedi non valide
