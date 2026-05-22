-- Per-cluster summary: how many papers, which years dominate,
-- representative title (the most recent in the cluster).
WITH ranked AS (
    SELECT
        t.cluster_id,
        t.top_terms,
        p.title,
        p.pub_year,
        ROW_NUMBER() OVER (
            PARTITION BY t.cluster_id
            ORDER BY p.pub_year DESC, p.pmid DESC
        ) AS rn
    FROM topics t
    JOIN papers p ON p.pmid = t.pmid
    WHERE p.pub_year IS NOT NULL
)
SELECT
    cluster_id,
    COUNT(*)                                 AS papers_in_cluster,
    MIN(pub_year)                            AS earliest_year,
    MAX(pub_year)                            AS latest_year,
    MAX(CASE WHEN rn = 1 THEN top_terms END) AS top_terms,
    MAX(CASE WHEN rn = 1 THEN title END)     AS exemplar_title
FROM ranked
GROUP BY cluster_id
ORDER BY papers_in_cluster DESC;
