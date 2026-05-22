# PubMed Bibliometric Pipeline

End-to-end pipeline that pulls publication metadata from PubMed (NCBI Entrez E-utilities), stores it in SQLite, runs NLP over the abstracts (TF-IDF + k-means clustering, emerging-term detection, MeSH analysis), exposes the dataset via parameterized SQL queries, and serves a Streamlit dashboard on top.

The problem space — quantitative mapping of a scientific literature, with attention to topic emergence, institutional concentration, and co-authorship structure — is directly inspired by CSET's *Map of Science* and similar bibliometric work. This repo is a self-contained reference implementation on a much smaller scale, built to demonstrate the workflow rather than replace those tools.

## What the pipeline does

```
                                  ┌──────────────────┐
                                  │  Entrez ESearch  │
                                  │  Entrez EFetch   │
                                  └────────┬─────────┘
                                           │ XML records
                                           ▼
                          ┌────────────────────────────────┐
                          │   src/ingest.py — parse,       │
                          │   normalize, upsert to SQLite  │
                          └────────────────┬───────────────┘
                                           │
        ┌──────────────────────────────────┼──────────────────────────────────┐
        ▼                                  ▼                                  ▼
┌────────────────┐               ┌────────────────┐                ┌────────────────┐
│  sql/*.sql     │               │  src/nlp.py    │                │ src/network.py │
│  CTEs +        │               │  TF-IDF +      │                │ co-authorship  │
│  window fns    │               │  k-means       │                │ + institutions │
└───────┬────────┘               └────────┬───────┘                └────────┬───────┘
        │                                 │                                 │
        └──────────────────┬──────────────┴──────────────┬──────────────────┘
                           ▼                             ▼
                  ┌──────────────────┐         ┌──────────────────┐
                  │ Streamlit app    │         │ Ad-hoc analysis  │
                  │ (app/)           │         │ (notebooks/, CLI)│
                  └──────────────────┘         └──────────────────┘
```

## Schema

SQLite, four tables:

| Table        | Columns                                                                       |
| ------------ | ----------------------------------------------------------------------------- |
| `papers`     | pmid · title · abstract · journal · pub_year · pub_date · doi · query_topic   |
| `authors`    | pmid · position · last_name · fore_name · affiliation                         |
| `mesh_terms` | pmid · term · major_topic                                                     |
| `topics`     | pmid · cluster_id · top_terms (JSON)                                          |

Full DDL: [src/db.py](src/db.py).

## Quickstart

```bash
pip install -r requirements.txt

# 1. Ingest. Override --email if you have one (Entrez asks; otherwise rate-limited).
python src/ingest.py \
    --query "clinical decision support AND artificial intelligence" \
    --retmax 300 --mindate 2015 --maxdate 2025

# 2. NLP — populates the topics table and prints emerging-term deltas.
python src/nlp.py --clusters 6

# 3. Run any SQL question — schema is documented, queries are portable.
sqlite3 -header -column data/pubmed.db < sql/02_publication_growth.sql

# 4. Dashboard.
streamlit run app/streamlit_app.py
```

## Sample output

A run against `clinical decision support AND artificial intelligence` (300 records, 2015–2025) produces, among other things:

**Top institutions** (parsed from author affiliations):

| institution                  | papers |
| ---------------------------- | ------ |
| University of California     | 9      |
| Stanford University          | 7      |
| University of Toronto        | 4      |
| Massachusetts General Hospital | 4    |
| Brigham and Women's Hospital | 4      |
| Mayo Clinic                  | 3      |

**Emerging vocabulary** (recent 2y vs. prior, TF-IDF delta):

| term      | recent | prior | Δ      |
| --------- | ------ | ----- | ------ |
| chatgpt   | 0.029  | 0.000 | +0.029 |
| ai        | 0.049  | 0.025 | +0.024 |
| radiomics | 0.031  | 0.009 | +0.022 |
| llms      | 0.014  | 0.004 | +0.010 |

**Topic clusters** (TF-IDF + k-means, top terms):

- *patients · machine learning · risk · model · prediction* (89 papers)
- *radiomics · features · deep learning · ci · validation* (60 papers)
- *artificial intelligence · care · tools · health* (49 papers)
- *chatgpt · language models · llms · accuracy · treatment* (36 papers)

## SQL queries

Each script in [sql/](sql/) answers one analytical question:

| File                                            | Question                                                       | Techniques                |
| ----------------------------------------------- | -------------------------------------------------------------- | ------------------------- |
| [01_top_institutions.sql](sql/01_top_institutions.sql) | Which institutions appear most often as primary affiliations?  | CTE, string parsing       |
| [02_publication_growth.sql](sql/02_publication_growth.sql) | Year-over-year growth, cumulative total, % change.            | Window fns (`SUM OVER`, `LAG`) |
| [03_top_mesh_terms.sql](sql/03_top_mesh_terms.sql)         | Most common MeSH tags and major-topic share.                   | Aggregation, `HAVING`     |
| [04_coauthor_pairs.sql](sql/04_coauthor_pairs.sql)         | Frequent co-author pairs.                                      | Self-join, dedup ordering |
| [05_cluster_summary.sql](sql/05_cluster_summary.sql)       | Per-cluster size, year span, exemplar title.                   | `ROW_NUMBER OVER`, CTE    |

## Design notes

- **No API key required.** Entrez allows 3 requests/sec anonymously; `ingest.py` sleeps between batches to stay under the limit. Add `--email` to identify yourself (Entrez requests this).
- **TF-IDF + k-means over BERTopic.** Picked deliberately: the corpus here is small (hundreds to low thousands of abstracts), and a sparse linear model is interpretable, fast, and doesn't require a GPU. Swap in BERTopic by replacing `cluster_abstracts` in [src/nlp.py](src/nlp.py) — the contract (DataFrame in, `(pmid, cluster_id, top_terms)` out) is the same.
- **Institution parsing is heuristic.** Affiliations are free text; the parser in [src/network.py](src/network.py) prefers parent-institution clauses ("Stanford University") over sub-units ("Department of Radiology"). A production pipeline would resolve to ROR or GRID identifiers — left as a follow-up.
- **Idempotent ingestion.** `upsert` uses `INSERT OR REPLACE` keyed on PMID. Re-running the same query updates records in place.

## Repo layout

```
pubmed-bibliometrics/
├── src/
│   ├── ingest.py        # Entrez ESearch + EFetch, XML parse, SQLite upsert
│   ├── db.py            # schema + connection helpers
│   ├── nlp.py           # TF-IDF, k-means, emerging-term detection
│   └── network.py       # co-authorship graph + institution table
├── sql/                 # five analytical queries (CTEs, window fns, self-joins)
├── app/
│   └── streamlit_app.py # dashboard over the populated DB
├── data/                # SQLite DB lives here (gitignored)
└── requirements.txt
```
