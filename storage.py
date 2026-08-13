import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone

# absolute path - a relative one would open a fresh db if cwd isn't the repo root
_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_hearings.db_")


def create_table() -> None:
    conn = sqlite3.connect(_DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS meetings (
        name TEXT,
        date TEXT,
        url TEXT PRIMARY KEY
    )""")
    conn.commit()
    conn.close()

def add_meeting(name, date, url) -> None:
    conn = sqlite3.connect(_DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO meetings VALUES (?,?,?)", (name, date, url))
    conn.commit()
    conn.close()

def is_new(url) -> bool:
    conn = sqlite3.connect(_DB_PATH)
    c = conn.cursor()
    value = c.execute("SELECT 1 FROM meetings WHERE url = ?", (url,)).fetchone() is None
    conn.close()
    return value


# speaker identification: entities (people/orgs), mentions that resolve to
# them, and the testimony those mentions gave. match_confidence below the
# threshold routes a mention to manual review.
REVIEW_CONFIDENCE_THRESHOLD = 0.75


def create_speaker_tables() -> None:
    conn = sqlite3.connect(_DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS entities (
        entity_id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        canonical_name TEXT NOT NULL,
        aka TEXT,
        created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS entity_mentions (
        mention_id TEXT PRIMARY KEY,
        raw_name TEXT NOT NULL,
        hearing_id TEXT NOT NULL,
        resolved_entity_id TEXT,
        match_method TEXT,
        match_confidence REAL,
        review_status TEXT DEFAULT 'unreviewed',
        created_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS testimony (
        testimony_id TEXT PRIMARY KEY,
        mention_id TEXT NOT NULL,
        hearing_id TEXT NOT NULL,
        committee TEXT,
        hearing_date TEXT,
        role TEXT,
        affiliation TEXT,
        title TEXT,
        position TEXT,
        quotes TEXT,
        confidence REAL,
        created_at TEXT NOT NULL
    )""")
    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_entity_by_name(name, entity_type):
    """Case-insensitive match against canonical_name or aka. Returns entity_id or None."""
    conn = sqlite3.connect(_DB_PATH)
    c = conn.cursor()
    rows = c.execute(
        "SELECT entity_id, canonical_name, aka FROM entities WHERE entity_type = ?", (entity_type,)
    ).fetchall()
    conn.close()
    target = name.strip().lower()
    for entity_id, canonical_name, aka_json in rows:
        names = [canonical_name] + (json.loads(aka_json) if aka_json else [])
        if target in [n.strip().lower() for n in names]:
            return entity_id
    return None


def add_entity(canonical_name, entity_type) -> str:
    """Find-or-create, returns the entity_id."""
    existing = find_entity_by_name(canonical_name, entity_type)
    if existing:
        return existing
    entity_id = hashlib.sha1(f"{entity_type}|{canonical_name.strip().lower()}".encode()).hexdigest()[:16]
    conn = sqlite3.connect(_DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO entities VALUES (?,?,?,?,?)",
        (entity_id, entity_type, canonical_name, json.dumps([]), _now()),
    )
    conn.commit()
    conn.close()
    return entity_id


def add_alias(entity_id, alias_name) -> None:
    """Record alias_name (e.g. an acronym) as a known alt name for entity_id."""
    conn = sqlite3.connect(_DB_PATH)
    c = conn.cursor()
    row = c.execute("SELECT canonical_name, aka FROM entities WHERE entity_id = ?", (entity_id,)).fetchone()
    if row:
        canonical_name, aka_json = row
        names = json.loads(aka_json) if aka_json else []
        if alias_name != canonical_name and alias_name not in names:
            names.append(alias_name)
            c.execute("UPDATE entities SET aka = ? WHERE entity_id = ?", (json.dumps(names), entity_id))
            conn.commit()
    conn.close()


def add_mention(mention_id, raw_name, hearing_id, resolved_entity_id, match_method, match_confidence) -> None:
    review_status = 'unreviewed' if (match_confidence or 0) < REVIEW_CONFIDENCE_THRESHOLD else 'verified'
    conn = sqlite3.connect(_DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO entity_mentions VALUES (?,?,?,?,?,?,?,?)",
        (mention_id, raw_name, hearing_id, resolved_entity_id, match_method, match_confidence, review_status, _now()),
    )
    conn.commit()
    conn.close()


def add_testimony(testimony_id, mention_id, hearing_id, committee, hearing_date,
                   role, affiliation, title, position, quotes, confidence) -> None:
    conn = sqlite3.connect(_DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO testimony VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (testimony_id, mention_id, hearing_id, committee, hearing_date, role,
         affiliation, title, position, json.dumps(quotes), confidence, _now()),
    )
    conn.commit()
    conn.close()


def save_identification(result, hearing_id, committee=None, hearing_date=None) -> dict:
    """Persists speakers.pipeline.identify_speakers() output: entities,
    entity_mentions, testimony rows. Returns row counts."""
    create_speaker_tables()
    n_mentions = n_testimony = 0

    for a in result.get("attendance", []):
        entity_id = add_entity(a["name"], "legislator")
        mention_id = hashlib.sha1(f"{hearing_id}|roll_call|{a['name'].lower()}".encode()).hexdigest()[:16]
        add_mention(mention_id, a["name"], hearing_id, entity_id, "roll_call", a.get("match_confidence", 0.5))
        n_mentions += 1

    for row in result.get("testimony", []):
        entity_type = 'legislator' if row["role"] == "legislator" else 'witness'
        entity_id = add_entity(row["name"], entity_type)
        mention_id = hashlib.sha1(
            f"{hearing_id}|{row['role']}|{row['name'].lower()}|{row.get('start')}".encode()
        ).hexdigest()[:16]
        add_mention(mention_id, row["name"], hearing_id, entity_id, row["match_method"], row["match_confidence"])
        n_mentions += 1

        affiliation = row.get("affiliation")
        if affiliation:
            org_canon = row.get("affiliation_canonical") or affiliation
            org_id = add_entity(org_canon, "organization")
            if affiliation != org_canon:
                add_alias(org_id, affiliation)

        testimony_id = hashlib.sha1(f"{mention_id}|{row.get('start')}".encode()).hexdigest()[:16]
        add_testimony(
            testimony_id, mention_id, hearing_id, committee, hearing_date,
            row["role"], affiliation, row.get("title"), row["position"],
            row["quotes"], row["confidence"],
        )
        n_testimony += 1

    return {"mentions": n_mentions, "testimony": n_testimony}

