-- Top co-authorship pairs across the corpus.
-- Self-join on the authors table within each PMID, dedup with a < b ordering.
WITH normed AS (
    SELECT
        pmid,
        TRIM(last_name) || ' ' || COALESCE(SUBSTR(TRIM(fore_name), 1, 1), '') AS author
    FROM authors
    WHERE last_name IS NOT NULL
)
SELECT
    a1.author                       AS author_a,
    a2.author                       AS author_b,
    COUNT(DISTINCT a1.pmid)         AS shared_papers
FROM normed a1
JOIN normed a2
  ON a1.pmid = a2.pmid
 AND a1.author < a2.author
GROUP BY a1.author, a2.author
HAVING shared_papers >= 2
ORDER BY shared_papers DESC, a1.author
LIMIT 25;
