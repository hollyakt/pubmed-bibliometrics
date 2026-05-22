"""Streamlit dashboard for the PubMed bibliometric pipeline.

Run with: streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from db import connect, DB_PATH  # noqa: E402
from nlp import emerging_terms, mesh_distribution  # noqa: E402
from network import institution_table  # noqa: E402


st.set_page_config(page_title="PubMed Bibliometrics", layout="wide")
st.title("PubMed Bibliometric Pipeline")

if not DB_PATH.exists():
    st.warning(
        "No database yet. Run "
        "`python src/ingest.py --query '<your query>' --retmax 200` first."
    )
    st.stop()


@st.cache_data
def load_meta() -> dict:
    with connect() as c:
        n = c.execute("SELECT COUNT(*) FROM papers").fetchone()[0]
        years = pd.read_sql(
            "SELECT pub_year, COUNT(*) AS papers FROM papers "
            "WHERE pub_year IS NOT NULL GROUP BY pub_year ORDER BY pub_year",
            c,
        )
        topics = pd.read_sql("SELECT DISTINCT query_topic FROM papers", c)
    return {"n": n, "years": years, "topics": topics["query_topic"].tolist()}


meta = load_meta()
col1, col2, col3 = st.columns(3)
col1.metric("Papers in DB", meta["n"])
col2.metric("Year range",
            f"{int(meta['years'].pub_year.min())}–{int(meta['years'].pub_year.max())}"
            if not meta["years"].empty else "—")
col3.metric("Query topics", len(meta["topics"]))

st.subheader("Publications by year")
st.plotly_chart(
    px.bar(meta["years"], x="pub_year", y="papers"),
    use_container_width=True,
)

tab1, tab2, tab3, tab4 = st.tabs(
    ["Top institutions", "MeSH terms", "Emerging vocabulary", "Topic clusters"]
)

with tab1:
    st.caption("Affiliation strings parsed with the heuristic in src/network.py.")
    st.dataframe(institution_table().head(25), use_container_width=True)

with tab2:
    md = mesh_distribution(top_n=30)
    st.dataframe(md, use_container_width=True)
    st.plotly_chart(
        px.bar(md.head(15), x="n", y="term", orientation="h").update_yaxes(autorange="reversed"),
        use_container_width=True,
    )

with tab3:
    window = st.slider("Recent window (years)", 1, 5, 2)
    et = emerging_terms(window_recent=window, top_n=25)
    if et.empty:
        st.info("Not enough year spread to compute emerging terms. Ingest a broader date range.")
    else:
        st.dataframe(et, use_container_width=True)
        st.plotly_chart(
            px.bar(et.head(15), x="delta", y="term", orientation="h")
              .update_yaxes(autorange="reversed"),
            use_container_width=True,
        )

with tab4:
    with connect() as c:
        topics = pd.read_sql(
            """SELECT t.cluster_id, t.top_terms, COUNT(*) AS n,
                      MIN(p.pub_year) AS earliest, MAX(p.pub_year) AS latest
               FROM topics t JOIN papers p ON p.pmid = t.pmid
               WHERE p.pub_year IS NOT NULL
               GROUP BY t.cluster_id, t.top_terms ORDER BY n DESC""",
            c,
        )
    if topics.empty:
        st.info("Topic table is empty. Run `python src/nlp.py` to populate it.")
    else:
        topics["top_terms"] = topics["top_terms"].map(
            lambda j: ", ".join(json.loads(j)[:6])
        )
        st.dataframe(topics, use_container_width=True)
