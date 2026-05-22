-- Top MeSH terms with the share of papers tagged as a major topic.
SELECT
    term,
    COUNT(*)                                                       AS n_papers,
    SUM(major_topic)                                               AS major_topic_count,
    ROUND(100.0 * SUM(major_topic) / COUNT(*), 1)                  AS major_topic_pct
FROM mesh_terms
GROUP BY term
HAVING n_papers >= 3
ORDER BY n_papers DESC, major_topic_pct DESC
LIMIT 30;
