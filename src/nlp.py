"""Lightweight NLP layer: TF-IDF + k-means clustering, keyword extraction,
emerging-term detection over time. Designed to work on the SQLite store
produced by src/ingest.py.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from db import connect

DEFAULT_STOPWORDS = "english"


def load_corpus() -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql(
            "SELECT pmid, pub_year, COALESCE(title,'') || '. ' || COALESCE(abstract,'') AS text "
            "FROM papers WHERE abstract IS NOT NULL",
            conn,
        )


def cluster_abstracts(df: pd.DataFrame, n_clusters: int = 6, top_n: int = 8) -> pd.DataFrame:
    """Cluster abstracts with TF-IDF + k-means; attach top terms per cluster."""
    vec = TfidfVectorizer(
        max_df=0.85, min_df=2, ngram_range=(1, 2),
        stop_words=DEFAULT_STOPWORDS, max_features=5000,
    )
    X = vec.fit_transform(df["text"])
    k = min(n_clusters, max(2, X.shape[0] // 5))
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(X)

    terms = np.array(vec.get_feature_names_out())
    cluster_terms: dict[int, list[str]] = {}
    for ci in range(k):
        center = km.cluster_centers_[ci]
        top_idx = center.argsort()[::-1][:top_n]
        cluster_terms[ci] = [str(t) for t in terms[top_idx]]

    out = df[["pmid"]].copy()
    out["cluster_id"] = labels
    out["top_terms"] = out["cluster_id"].map(lambda c: json.dumps(cluster_terms[c]))
    return out


def write_topics(topics_df: pd.DataFrame) -> int:
    with connect() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM topics")
        cur.executemany(
            "INSERT INTO topics (pmid, cluster_id, top_terms) VALUES (?, ?, ?)",
            list(topics_df[["pmid", "cluster_id", "top_terms"]].itertuples(index=False, name=None)),
        )
        return cur.rowcount


def emerging_terms(window_recent: int = 2, top_n: int = 20) -> pd.DataFrame:
    """Compare unigram frequency in the most recent `window_recent` years
    vs. all prior years. Returns terms with the largest positive delta.
    """
    df = load_corpus()
    if df.empty or df["pub_year"].dropna().empty:
        return pd.DataFrame(columns=["term", "recent_freq", "prior_freq", "delta"])

    max_year = int(df["pub_year"].dropna().max())
    cutoff = max_year - window_recent + 1

    vec = TfidfVectorizer(
        max_df=0.9, min_df=2, ngram_range=(1, 1),
        stop_words=DEFAULT_STOPWORDS, max_features=3000,
    )
    X = vec.fit_transform(df["text"])
    terms = vec.get_feature_names_out()

    recent_mask = (df["pub_year"] >= cutoff).values
    if recent_mask.sum() == 0 or (~recent_mask).sum() == 0:
        return pd.DataFrame(columns=["term", "recent_freq", "prior_freq", "delta"])

    recent_mean = np.asarray(X[recent_mask].mean(axis=0)).ravel()
    prior_mean = np.asarray(X[~recent_mask].mean(axis=0)).ravel()
    delta = recent_mean - prior_mean
    order = delta.argsort()[::-1][:top_n]

    return pd.DataFrame({
        "term": terms[order],
        "recent_freq": recent_mean[order].round(5),
        "prior_freq": prior_mean[order].round(5),
        "delta": delta[order].round(5),
    })


def top_keywords_overall(top_n: int = 30) -> list[tuple[str, float]]:
    df = load_corpus()
    vec = TfidfVectorizer(
        max_df=0.85, min_df=2, ngram_range=(1, 2),
        stop_words=DEFAULT_STOPWORDS, max_features=5000,
    )
    X = vec.fit_transform(df["text"])
    scores = np.asarray(X.mean(axis=0)).ravel()
    terms = vec.get_feature_names_out()
    order = scores.argsort()[::-1][:top_n]
    return list(zip(terms[order].tolist(), scores[order].round(5).tolist()))


def mesh_distribution(top_n: int = 25) -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql(
            f"""SELECT term, COUNT(*) AS n FROM mesh_terms
                GROUP BY term ORDER BY n DESC LIMIT {top_n}""",
            conn,
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clusters", type=int, default=6)
    args = ap.parse_args()

    df = load_corpus()
    print(f"Loaded {len(df)} abstracts")
    topics = cluster_abstracts(df, n_clusters=args.clusters)
    n = write_topics(topics)
    print(f"Wrote {n} topic assignments")
    for ci, grp in topics.groupby("cluster_id"):
        top = json.loads(grp.iloc[0]["top_terms"])
        print(f"  cluster {ci} (n={len(grp)}): {', '.join(top)}")
    print("\nEmerging terms (last 2y vs prior):")
    print(emerging_terms().to_string(index=False))


if __name__ == "__main__":
    main()
