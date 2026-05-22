"""Co-authorship and institution networks built from the authors table."""
from __future__ import annotations

import re
from collections import Counter
from itertools import combinations

import networkx as nx
import pandas as pd

from db import connect


def _norm_author(row) -> str | None:
    last = (row["last_name"] or "").strip()
    fore = (row["fore_name"] or "").strip()
    if not last:
        return None
    initial = fore[:1].upper() if fore else ""
    return f"{last.title()} {initial}".strip()


_PRIMARY_INSTITUTION_KEYWORDS = (
    "university", "institute", "hospital", "school of medicine", "college",
    "clinic", "academy", "foundation",
)
_SECONDARY_INSTITUTION_KEYWORDS = (
    "center", "centre", "laboratory", "school",
)


def _extract_institution(aff: str | None) -> str | None:
    """Heuristic: prefer the clause naming the parent institution
    (university, hospital, institute) over sub-units like "Department of X".
    Falls back to the first non-departmental clause.
    """
    if not aff:
        return None
    aff = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "", aff)   # drop emails
    parts = [p.strip(" .;") for p in aff.split(",") if p.strip()]
    if not parts:
        return None

    for p in parts:
        low = p.lower()
        if any(k in low for k in _PRIMARY_INSTITUTION_KEYWORDS):
            return re.sub(r"\s+", " ", p)
    for p in parts:
        low = p.lower()
        if any(k in low for k in _SECONDARY_INSTITUTION_KEYWORDS) \
                and not low.startswith("department"):
            return re.sub(r"\s+", " ", p)
    for p in parts:
        if not p.lower().startswith("department"):
            return re.sub(r"\s+", " ", p)
    return re.sub(r"\s+", " ", parts[0])


def coauthor_graph(min_papers: int = 2) -> nx.Graph:
    with connect() as conn:
        df = pd.read_sql("SELECT pmid, last_name, fore_name FROM authors", conn)
    df["author"] = df.apply(_norm_author, axis=1)
    df = df.dropna(subset=["author"])

    counts = df["author"].value_counts()
    keep = set(counts[counts >= min_papers].index)
    df = df[df["author"].isin(keep)]

    G = nx.Graph()
    for author, n in counts.items():
        if author in keep:
            G.add_node(author, papers=int(n))
    for _, grp in df.groupby("pmid"):
        for a, b in combinations(sorted(set(grp["author"])), 2):
            if G.has_edge(a, b):
                G[a][b]["weight"] += 1
            else:
                G.add_edge(a, b, weight=1)
    return G


def institution_table() -> pd.DataFrame:
    with connect() as conn:
        df = pd.read_sql(
            "SELECT pmid, affiliation FROM authors WHERE affiliation IS NOT NULL", conn
        )
    df["institution"] = df["affiliation"].map(_extract_institution)
    df = df.dropna(subset=["institution"])
    grouped = df.groupby("institution")["pmid"].nunique().sort_values(ascending=False)
    return grouped.rename("papers").reset_index()


if __name__ == "__main__":
    G = coauthor_graph(min_papers=2)
    print(f"Co-author graph: {G.number_of_nodes()} authors, {G.number_of_edges()} edges")
    if G.number_of_nodes():
        top = sorted(G.degree, key=lambda x: x[1], reverse=True)[:10]
        print("Most connected authors:")
        for name, deg in top:
            print(f"  {name}: {deg} collaborators, {G.nodes[name]['papers']} papers")

    print("\nTop institutions:")
    print(institution_table().head(15).to_string(index=False))
