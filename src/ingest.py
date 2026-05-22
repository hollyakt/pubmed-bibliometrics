"""PubMed (NCBI Entrez E-utilities) ingestion.

Pulls IDs for a topic query via ESearch, fetches MEDLINE XML via EFetch,
parses titles / abstracts / authors / affiliations / MeSH terms,
and writes them into the SQLite store defined in src/db.py.

Reference:
    https://www.ncbi.nlm.nih.gov/books/NBK25501/
"""
from __future__ import annotations

import argparse
import time
import xml.etree.ElementTree as ET
from typing import Iterable

import requests

from db import connect, init_db

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
TOOL = "pubmed-bibliometrics"
EMAIL = "noreply@example.com"   # Entrez asks for an email; override via --email


def search_pmids(query: str, retmax: int, mindate: int | None, maxdate: int | None,
                 email: str = EMAIL) -> list[str]:
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": retmax,
        "retmode": "json",
        "sort": "pub_date",
        "tool": TOOL,
        "email": email,
    }
    if mindate:
        params["mindate"] = str(mindate)
    if maxdate:
        params["maxdate"] = str(maxdate)
    r = requests.get(ESEARCH, params=params, timeout=30)
    r.raise_for_status()
    return r.json()["esearchresult"].get("idlist", [])


def fetch_records(pmids: list[str], email: str = EMAIL) -> ET.Element:
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "tool": TOOL,
        "email": email,
    }
    r = requests.post(EFETCH, data=params, timeout=60)
    r.raise_for_status()
    return ET.fromstring(r.content)


def _text(el: ET.Element | None) -> str | None:
    if el is None:
        return None
    text = "".join(el.itertext()).strip()
    return text or None


def parse_article(article: ET.Element) -> dict:
    pmid = _text(article.find(".//PMID"))
    title = _text(article.find(".//ArticleTitle"))
    abstract = " ".join(
        _text(node) or "" for node in article.findall(".//Abstract/AbstractText")
    ).strip() or None
    journal = _text(article.find(".//Journal/Title"))
    year_el = article.find(".//JournalIssue/PubDate/Year")
    medline_date = article.find(".//JournalIssue/PubDate/MedlineDate")
    if year_el is not None and (y := _text(year_el)):
        pub_year = int(y[:4]) if y[:4].isdigit() else None
    elif medline_date is not None and (md := _text(medline_date)):
        pub_year = int(md[:4]) if md[:4].isdigit() else None
    else:
        pub_year = None
    pub_date_parts = [
        _text(article.find(f".//JournalIssue/PubDate/{f}")) for f in ("Year", "Month", "Day")
    ]
    pub_date = "-".join(p for p in pub_date_parts if p) or None

    doi = None
    for aid in article.findall(".//ArticleIdList/ArticleId"):
        if aid.attrib.get("IdType") == "doi":
            doi = _text(aid)
            break

    authors = []
    for i, a in enumerate(article.findall(".//AuthorList/Author")):
        last = _text(a.find("LastName"))
        fore = _text(a.find("ForeName"))
        aff = _text(a.find(".//AffiliationInfo/Affiliation"))
        if last or fore:
            authors.append({"position": i, "last_name": last,
                           "fore_name": fore, "affiliation": aff})

    mesh = []
    for m in article.findall(".//MeshHeadingList/MeshHeading"):
        d = m.find("DescriptorName")
        if d is None or not _text(d):
            continue
        mesh.append({
            "term": _text(d),
            "major_topic": 1 if d.attrib.get("MajorTopicYN") == "Y" else 0,
        })

    return {
        "pmid": pmid, "title": title, "abstract": abstract, "journal": journal,
        "pub_year": pub_year, "pub_date": pub_date, "doi": doi,
        "authors": authors, "mesh": mesh,
    }


def upsert(records: Iterable[dict], topic: str) -> int:
    n = 0
    with connect() as conn:
        cur = conn.cursor()
        for rec in records:
            if not rec.get("pmid"):
                continue
            cur.execute(
                """INSERT OR REPLACE INTO papers
                   (pmid, title, abstract, journal, pub_year, pub_date, doi, query_topic)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (rec["pmid"], rec["title"], rec["abstract"], rec["journal"],
                 rec["pub_year"], rec["pub_date"], rec["doi"], topic),
            )
            cur.execute("DELETE FROM authors WHERE pmid = ?", (rec["pmid"],))
            cur.executemany(
                """INSERT INTO authors (pmid, position, last_name, fore_name, affiliation)
                   VALUES (?, ?, ?, ?, ?)""",
                [(rec["pmid"], a["position"], a["last_name"], a["fore_name"], a["affiliation"])
                 for a in rec["authors"]],
            )
            cur.execute("DELETE FROM mesh_terms WHERE pmid = ?", (rec["pmid"],))
            cur.executemany(
                """INSERT INTO mesh_terms (pmid, term, major_topic) VALUES (?, ?, ?)""",
                [(rec["pmid"], m["term"], m["major_topic"]) for m in rec["mesh"]],
            )
            n += 1
    return n


def ingest(query: str, retmax: int = 200, mindate: int | None = None,
           maxdate: int | None = None, batch: int = 100, email: str = EMAIL) -> int:
    init_db()
    pmids = search_pmids(query, retmax, mindate, maxdate, email=email)
    print(f"ESearch returned {len(pmids)} PMIDs for '{query}'")
    total = 0
    for i in range(0, len(pmids), batch):
        chunk = pmids[i:i + batch]
        root = fetch_records(chunk, email=email)
        records = [parse_article(a) for a in root.findall(".//PubmedArticle")]
        n = upsert(records, topic=query)
        total += n
        print(f"  batch {i // batch + 1}: stored {n} records (cumulative {total})")
        time.sleep(0.34)   # Entrez: max 3 requests/sec without API key
    return total


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--query", required=True,
                   help='PubMed query, e.g. "clinical decision support AND artificial intelligence"')
    p.add_argument("--retmax", type=int, default=200)
    p.add_argument("--mindate", type=int, default=None)
    p.add_argument("--maxdate", type=int, default=None)
    p.add_argument("--email", default=EMAIL)
    args = p.parse_args()
    n = ingest(args.query, retmax=args.retmax, mindate=args.mindate,
               maxdate=args.maxdate, email=args.email)
    print(f"Done. Ingested {n} records.")


if __name__ == "__main__":
    main()
