-- Top institutions by distinct papers, with author counts.
-- Uses the same first-clause heuristic as src/network.py for portability:
-- here we just trim everything before the first comma.
WITH affil_clean AS (
    SELECT
        a.pmid,
        TRIM(SUBSTR(a.affiliation, 1, INSTR(a.affiliation || ',', ',') - 1)) AS clause
    FROM authors a
    WHERE a.affiliation IS NOT NULL
)
SELECT
    clause                                  AS institution_clause,
    COUNT(DISTINCT pmid)                    AS papers,
    COUNT(*)                                AS author_mentions
FROM affil_clean
WHERE LOWER(clause) NOT LIKE 'department%'
GROUP BY clause
HAVING papers >= 2
ORDER BY papers DESC, author_mentions DESC
LIMIT 25;
