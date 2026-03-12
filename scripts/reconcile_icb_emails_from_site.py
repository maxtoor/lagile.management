#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
import ssl
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path


SEED_URLS = [
    "https://www.icb.cnr.it/tecnici-e-amministrativi/",
    "https://www.icb.cnr.it/ricercatori-e-tecnologi/",
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    text = (value or "").strip().lower()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = WS_RE.sub(" ", text)
    return text


def html_to_text(html: str) -> str:
    text = TAG_RE.sub(" ", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return normalize_text(text)


def crawl_icb_pages(max_pages: int = 300) -> list[dict]:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    visited = set()
    queue = list(SEED_URLS)
    pages = []

    while queue and len(visited) < max_pages:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if "html" not in ctype:
                    continue
                html = resp.read().decode("utf-8", "ignore")
        except Exception:
            continue

        text = html_to_text(html)
        emails = sorted(
            {
                e.lower().strip()
                for e in EMAIL_RE.findall(html)
                if e.lower().endswith("@cnr.it") or e.lower().endswith("@icb.cnr.it")
            }
        )
        pages.append({"url": url, "text": text, "emails": emails})

        for href in HREF_RE.findall(html):
            abs_url = urllib.parse.urljoin(url, href.strip())
            if not abs_url.startswith("https://www.icb.cnr.it/"):
                continue
            if any(k in abs_url for k in ["/teams/", "/tecnici-e-amministrativi", "/ricercatori-e-tecnologi"]):
                if abs_url not in visited:
                    queue.append(abs_url)

    return pages


def choose_email_for_person(first_name: str, last_name: str, pages: list[dict]) -> tuple[str, str, str]:
    first = normalize_text(first_name)
    last = normalize_text(last_name)
    full = f"{first} {last}".strip()
    rev = f"{last} {first}".strip()

    candidates = []
    for page in pages:
        text = page["text"]
        if not text:
            continue
        full_hit = bool(full and full in text)
        rev_hit = bool(rev and rev in text)
        first_hit = bool(first and first in text)
        last_hit = bool(last and last in text)
        # Strict policy: prefer pages where both name and surname are present.
        # This avoids noisy matches on list pages where only surname-like tokens appear.
        if not (full_hit or rev_hit or (first_hit and last_hit)):
            continue
        for email in page["emails"]:
            score = 0
            local = email.split("@", 1)[0]
            if last and last in normalize_text(local):
                score += 3
            if first and first in normalize_text(local):
                score += 2
            if full_hit or rev_hit:
                score += 3
            elif last_hit:
                score += 1
            candidates.append((score, email, page["url"]))

    if not candidates:
        return "", "", "NON_TROVATA"

    candidates.sort(key=lambda x: (-x[0], x[1]))
    top_score = candidates[0][0]
    top = [c for c in candidates if c[0] == top_score]
    unique_emails = sorted({c[1] for c in top})
    if len(unique_emails) == 1:
        source = next(c[2] for c in top if c[1] == unique_emails[0])
        return unique_emails[0], source, "TROVATA_UNIVOCA"
    return "|".join(unique_emails), top[0][2], "AMBIGUA"


def reconcile(csv_in: Path, csv_out: Path, max_pages: int) -> dict:
    pages = crawl_icb_pages(max_pages=max_pages)
    rows = list(csv.DictReader(csv_in.open("r", encoding="utf-8-sig", newline="")))

    out_rows = []
    counts = {"TROVATA_UNIVOCA": 0, "AMBIGUA": 0, "NON_TROVATA": 0, "UGUALE": 0, "DIVERSA": 0}

    for row in rows:
        old_email = (row.get("email") or "").strip().lower()
        last = (row.get("lastname") or "").strip()
        first = (row.get("name") or "").strip()

        found_email, source_url, status = choose_email_for_person(first, last, pages)
        counts[status] += 1

        compare = ""
        if status == "TROVATA_UNIVOCA":
            compare = "UGUALE" if found_email == old_email else "DIVERSA"
            counts[compare] += 1

        out_rows.append(
            {
                "lastname": last,
                "name": first,
                "email_csv": old_email,
                "email_trovata_sito": found_email,
                "esito_ricerca": status,
                "confronto_csv_vs_sito": compare,
                "fonte": source_url,
            }
        )

    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "lastname",
                "name",
                "email_csv",
                "email_trovata_sito",
                "esito_ricerca",
                "confronto_csv_vs_sito",
                "fonte",
            ],
        )
        writer.writeheader()
        writer.writerows(out_rows)

    return {
        "rows": len(rows),
        "pages": len(pages),
        "counts": counts,
        "output": str(csv_out.resolve()),
    }


def main():
    parser = argparse.ArgumentParser(description="Confronta email CSV ICB con email pubblicate sul sito ICB (matching per nome+cognome).")
    parser.add_argument("--csv-in", required=True, help="Percorso CSV input (header: email, lastname, name, ...)")
    parser.add_argument(
        "--csv-out",
        default="reports/icb_email_name_match.csv",
        help="Percorso CSV output report (default: reports/icb_email_name_match.csv)",
    )
    parser.add_argument("--max-pages", type=int, default=300, help="Numero massimo pagine da scansionare (default: 300)")
    args = parser.parse_args()

    result = reconcile(Path(args.csv_in), Path(args.csv_out), args.max_pages)
    print(f"Report: {result['output']}")
    print(f"Righe CSV: {result['rows']}")
    print(f"Pagine scansionate: {result['pages']}")
    print(f"TROVATA_UNIVOCA: {result['counts']['TROVATA_UNIVOCA']}")
    print(f"AMBIGUA: {result['counts']['AMBIGUA']}")
    print(f"NON_TROVATA: {result['counts']['NON_TROVATA']}")
    print(f"UGUALE: {result['counts']['UGUALE']}")
    print(f"DIVERSA: {result['counts']['DIVERSA']}")


if __name__ == "__main__":
    main()
