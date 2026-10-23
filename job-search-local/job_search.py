#!/usr/bin/env python3
"""Local, rules-based job feed collector; standard library only."""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sqlite3
import sys
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse


class TextOnly(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean_text(value: object) -> str:
    if not value:
        return ""
    parser = TextOnly()
    try:
        parser.feed(str(value))
        return re.sub(r"\s+", " ", html.unescape(" ".join(parser.parts))).strip()
    except Exception:
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(value))).strip()


def norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def has_term(text: str, term: str) -> bool:
    normalized_term = norm(term)
    return bool(normalized_term and f" {normalized_term} " in f" {text} ")


def parse_date(value: str) -> str:
    if not value:
        return ""
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value[:80]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def first_text(element: ET.Element, *names: str) -> str:
    wanted = {n.lower() for n in names}
    for child in element.iter():
        if local_name(child.tag) in wanted:
            if child.text and child.text.strip():
                return child.text.strip()
            href = child.attrib.get("href")
            if href:
                return href.strip()
    return ""


def parse_feed(raw: bytes, feed_name: str) -> list[dict[str, str]]:
    root = ET.fromstring(raw)
    jobs: list[dict[str, str]] = []
    # RSS and Atom share item/entry data, but their link/title shapes differ.
    entries = [e for e in root.iter() if local_name(e.tag) in {"item", "entry"}]
    for entry in entries:
        title = first_text(entry, "title")
        link = first_text(entry, "link")
        if not link:
            guid = first_text(entry, "guid", "id")
            if guid.startswith(("http://", "https://")):
                link = guid
        if not title or not link:
            continue
        description = first_text(entry, "description", "summary", "content", "encoded")
        company = first_text(entry, "company", "author", "creator")
        published = first_text(entry, "pubdate", "published", "updated", "date")
        jobs.append({
            "source": feed_name,
            "title": clean_text(title),
            "company": clean_text(company),
            "location": "",
            "description": clean_text(description),
            "url": link.strip(),
            "published": parse_date(published),
        })
    return jobs


def score_job(job: dict[str, str], config: dict) -> tuple[int, list[str], str]:
    title = norm(job.get("title", ""))
    body = norm(" ".join((job.get("title", ""), job.get("company", ""),
                          job.get("location", ""), job.get("description", ""))))
    filters = config.get("filters", {})
    remote_hits = [t for t in filters.get("remote_terms", []) if has_term(body, t)]
    peru_hits = [t for t in filters.get("peru_terms", []) if has_term(body, t)]
    excluded = [t for t in filters.get("exclude_terms", []) if has_term(body, t)]
    top_score, top_track, top_reasons = 0, "Sin coincidencia clara", []

    for track in config.get("tracks", []):
        title_hits = [t for t in track.get("title_terms", []) if has_term(title, t)]
        skill_hits = [t for t in track.get("skill_terms", []) if has_term(body, t)]
        avoid_hits = [t for t in track.get("avoid_terms", []) if has_term(body, t)]
        # Cap repeated matches so long descriptions cannot win by keyword stuffing.
        points = min(40, 20 * len(title_hits)) + min(36, 4 * len(skill_hits))
        if remote_hits:
            points += 8
        if peru_hits:
            points += 6
        points -= min(40, 20 * len(avoid_hits))
        points -= min(40, 20 * len(excluded))
        reasons = []
        if title_hits:
            reasons.append("título: " + ", ".join(title_hits[:3]))
        if skill_hits:
            reasons.append("perfil: " + ", ".join(skill_hits[:5]))
        if remote_hits:
            reasons.append("remoto")
        if peru_hits:
            reasons.append("Perú/LatAm compatible")
        if avoid_hits or excluded:
            reasons.append("revisar exclusión: " + ", ".join((avoid_hits + excluded)[:3]))
        if points > top_score:
            top_score, top_track, top_reasons = points, track["name"], reasons
    return max(0, top_score), top_reasons, top_track


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        config = json.load(f)
    if not isinstance(config.get("feeds"), list) or not isinstance(config.get("tracks"), list):
        raise ValueError("'feeds' y 'tracks' deben ser listas en config.json")
    for feed in config["feeds"]:
        if not isinstance(feed, dict) or not isinstance(feed.get("url"), str) or not feed["url"].strip():
            raise ValueError("Cada feed debe tener name y url")
        parsed_url = urlparse(feed["url"].strip())
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise ValueError("Cada feed debe usar una URL HTTP o HTTPS válida")
        feed["url"] = feed["url"].strip()
        if not feed.get("name"):
            feed["name"] = feed["url"]
    return config


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path)
    db.execute("""CREATE TABLE IF NOT EXISTS jobs (
        url TEXT PRIMARY KEY, source TEXT, title TEXT, company TEXT, location TEXT,
        description TEXT, published TEXT, first_seen TEXT, score INTEGER,
        track TEXT, reasons TEXT, status TEXT DEFAULT 'nueva'
    )""")
    db.commit()
    return db


def ingest(config: dict, base: Path) -> tuple[int, int]:
    db_path = base / config.get("database", "jobs.sqlite3")
    db = connect(db_path)
    added = failed = 0
    for feed in config.get("feeds", []):
        name, url = feed.get("name", feed["url"]), feed["url"]
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "LocalJobSearch/1.0 (RSS reader)"})
            with urllib.request.urlopen(request, timeout=25) as response:
                raw = response.read(5_000_001)
            if len(raw) > 5_000_000:
                raise ValueError("feed supera 5 MB")
            jobs = parse_feed(raw, name)
            for job in jobs:
                score, reasons, track = score_job(job, config)
                cursor = db.execute("""INSERT OR IGNORE INTO jobs
                    (url, source, title, company, location, description, published, first_seen,
                     score, track, reasons) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (job["url"], job["source"], job["title"], job["company"], job["location"],
                     job["description"], job["published"], datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     score, track, "; ".join(reasons)))
                added += cursor.rowcount
            print(f"OK {name}: {len(jobs)} ofertas leídas")
        except (urllib.error.URLError, TimeoutError, ValueError, ET.ParseError) as exc:
            failed += 1
            print(f"ERROR {name}: {exc}", file=sys.stderr)
    db.commit()
    db.close()
    return added, failed


def export(config: dict, base: Path) -> int:
    db = connect(base / config.get("database", "jobs.sqlite3"))
    out = base / config.get("output_csv", "salida/ofertas.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = db.execute("""SELECT score, track, title, company, location, source, published,
        url, reasons, status FROM jobs ORDER BY score DESC, first_seen DESC""").fetchall()
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["puntuacion", "categoria", "puesto", "empresa", "ubicacion", "fuente",
                         "publicada", "url", "motivos", "estado"])
        writer.writerows([spreadsheet_safe_row(row) for row in rows])
    db.close()
    print(f"CSV actualizado: {out} ({len(rows)} ofertas)")
    return len(rows)


def spreadsheet_safe_row(row: tuple) -> list:
    """Prefix risky text cells so spreadsheet apps do not treat feed text as formulas."""
    safe = []
    for value in row:
        if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
            value = "'" + value
        safe.append(value)
    return safe


def main() -> int:
    parser = argparse.ArgumentParser(description="Búsqueda laboral local basada en RSS y reglas")
    parser.add_argument("command", nargs="?", choices=["run", "export"], default="run")
    parser.add_argument("--config", default="config.json", help="ruta del archivo de configuración")
    parser.add_argument("--check-config", action="store_true", help="validar configuración y salir")
    parser.add_argument("--export", action="store_true", help="exportar CSV después de descargar feeds")
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    try:
        config = load_config(config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Configuración inválida ({config_path}): {exc}", file=sys.stderr)
        return 2
    base = config_path.parent
    if args.check_config:
        print(f"Configuración válida: {len(config['feeds'])} feeds, {len(config['tracks'])} categorías")
        return 0
    if args.command == "export":
        export(config, base)
        return 0
    added, failed = ingest(config, base)
    print(f"Nuevas: {added}; feeds con error: {failed}")
    if args.export:
        export(config, base)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
