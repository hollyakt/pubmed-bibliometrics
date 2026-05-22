-- Year-over-year publication growth with a cumulative running total
-- and a percentage delta vs. the prior year (window function).
WITH yearly AS (
    SELECT
        pub_year                            AS year,
        COUNT(*)                            AS papers
    FROM papers
    WHERE pub_year IS NOT NULL
    GROUP BY pub_year
)
SELECT
    year,
    papers,
    SUM(papers) OVER (ORDER BY year)                                                     AS cumulative,
    LAG(papers) OVER (ORDER BY year)                                                     AS prev_year,
    ROUND(
        100.0 * (papers - LAG(papers) OVER (ORDER BY year))
              / NULLIF(LAG(papers) OVER (ORDER BY year), 0), 1
    )                                                                                    AS pct_change
FROM yearly
ORDER BY year;
