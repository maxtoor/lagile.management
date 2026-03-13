# Porting colori UI verso versione advanced

Questo documento riassume le modifiche colore stabilizzate nel fork Ubuntu 20 e puo essere usato come checklist per riportarle, in tutto o in parte, nella versione "advanced".

Obiettivo:
- mantenere la palette piu sobria e leggibile
- evitare sfondi decorativi troppo presenti
- usare il colore soprattutto per azioni e stati

## Stato di riferimento

Branch fork:
- `codex/ubuntu20-regression`

File sorgente principali:
- [`templates/employee_app.html`](/Users/master/Documents/projects/lagile.new/agile_work_ubuntu20/templates/employee_app.html)
- [`agile/static/agile/admin-theme.css`](/Users/master/Documents/projects/lagile.new/agile_work_ubuntu20/agile/static/agile/admin-theme.css)

## Principi visivi da mantenere

- sfondo pagina bianco o neutro, senza gradienti vistosi
- pannelli e card bianchi
- bordi grigio chiaro, uniformi
- testo grigio scuro neutro invece di verdi o toni troppo saturi
- colori accesi usati solo per pulsanti, link, badge e stati
- separare la gerarchia visiva con bordi, spaziature e ombre leggere, non con fondali colorati

## Token colore portale utente

Valori attualmente usati nel fork Ubuntu 20:

```css
--ink: #545d68;
--muted: #737d88;
--line: #d7dde6;
--accent: #56b5de;
--accent-strong: #3e9ec8;
--accent-soft: #e3f2fb;
--accent-2: #e7a542;
```

Decisioni UI applicate:
- `body` bianco
- card e pannelli bianchi
- menu e top strip bianchi
- footer bianco
- modali bianche
- calendario base bianco
- `.user-profile-item` con grigio chiarissimo `#f7f8fa`
- niente spazio riservato alla scrollbar verticale quando non serve

## Token colore admin

Valori attualmente usati nel fork Ubuntu 20:

```css
--agile-bg: #ffffff;
--agile-panel: #ffffff;
--agile-ink: #545d68;
--agile-muted: #737d88;
--agile-line: #d7dde6;
```

Decisioni UI applicate:
- sfondo pagina admin bianco
- header bianco
- breadcrumbs bianchi
- footer bianco
- moduli e inline group bianchi
- intestazioni moduli bianche
- login admin bianco
- link header admin con contrasto esplicito

## Checklist porting portale utente

Applicare nella versione advanced, in quest'ordine:

1. Portare o mappare i token colore principali.
2. Rendere bianchi sfondi globali e pannelli.
3. Rendere bianchi header, footer, menu e dropdown.
4. Mantenere i colori solo su:
   - pulsanti principali
   - warning
   - stati del calendario
   - link
5. Schiarire i box profilo utente con un grigio quasi bianco.
6. Verificare che i bordi laterali siano simmetrici quando non compare la scrollbar.

Selettori utili da cercare nella versione advanced:
- `body`
- `.card`
- `.page-top-strip`
- `.page-footer`
- `.main-menu-toggle`
- `.main-menu-panel`
- `.custom-select-panel`
- `.user-profile-item`
- `.calendar-day`
- `.calendar-weekday`
- `.details-day`

## Checklist porting admin

Applicare nella versione advanced, in quest'ordine:

1. Portare o mappare i token colore admin.
2. Rendere bianchi:
   - `html, body`
   - `#header`
   - `div.breadcrumbs`
   - `.admin-page-footer`
   - `.module`
   - `.inline-group`
3. Rendere bianche anche le intestazioni modulo e i `summary` dei blocchi collassabili.
4. Verificare il contrasto dei link nel blocco `#user-tools`.
5. Verificare login admin e modali.

Selettori utili da cercare nella versione advanced:
- `html, body`
- `#header`
- `div.breadcrumbs`
- `.admin-page-footer`
- `.module`
- `.inline-group`
- `#changelist-filter`
- `.module h2`
- `fieldset.module details > summary`
- `#user-tools a`
- `#user-tools button`

## Commit del fork Ubuntu 20 utili come riferimento

Portale utente:
- `164bdd5` `Refresh employee portal colors for Ubuntu 20 fork`
- `dd07d58` `Simplify employee portal background`
- `af4a3ab` `Use white surfaces in employee portal`
- `a08f183` `Align left edge by removing dual scrollbar gutter`
- `58f1477` `Remove reserved vertical scrollbar gutter`
- `281601f` `Lighten user profile item background`

Admin:
- `210b64d` `Use white admin surfaces in Ubuntu 20 fork`
- `5fcf4c1` `Fix admin header user link contrast`

## Nota operativa

Quando si fara il porting nella versione advanced:
- evitare di copiare blocchi interi alla cieca
- portare prima i token e poi le superfici principali
- fare commit piccoli e separati
- verificare sempre con hard refresh del browser dopo ogni step visivo
