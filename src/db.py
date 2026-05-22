"""SQLite schema and connection helpers for the bibliometric pipeline."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "pubmed.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    pmid          TEXT PRIMARY KEY,
    title         TEXT,
    abstract      TEXT,
    journal       TEXT,
    pub_year      INTEGER,
    pub_date      TEXT,
    doi           TEXT,
    query_topic   TEXT,
    ingested_at   TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS authors (
    pmid          TEXT NOT NULL,
    position      INTEGER NOT NULL,
    last_name     TEXT,
    fore_name     TEXT,
    affiliation   TEXT,
    PRIMARY KEY (pmid, position),
    FOREIGN KEY (pmid) REFERENCES papers(pmid)
);

CREATE TABLE IF NOT EXISTS mesh_terms (
    pmid          TEXT NOT NULL,
    term          TEXT NOT NULL,
    major_topic   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (pmid, term),
    FOREIGN KEY (pmid) REFERENCES papers(pmid)
);

CREATE TABLE IF NOT EXISTS topics (
    pmid          TEXT PRIMARY KEY,
    cluster_id    INTEGER,
    top_terms     TEXT,
    FOREIGN KEY (pmid) REFERENCES papers(pmid)
);

CREATE INDEX IF NOT EXISTS ix_papers_year   ON papers(pub_year);
CREATE INDEX IF NOT EXISTS ix_papers_topic  ON papers(query_topic);
CREATE INDEX IF NOT EXISTS ix_authors_last  ON authors(last_name);
CREATE INDEX IF NOT EXISTS ix_mesh_term     ON mesh_terms(term);
"""


def init_db(path: Path = DB_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
    return path


@contextmanager
def connect(path: Path = DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    p = init_db()
    print(f"Initialized SQLite DB at {p}")
