-- Scorecard over newline-delimited run-record rows (see README.md for the row shape).
-- Parameters: $runs (file glob), $safe_label (the label whose false use is costliest).
-- Output: long format, one row per (metric, label); value is NULL when the denominator is 0.
WITH runs AS (
    SELECT *
    FROM read_json(
        $runs,
        format = 'newline_delimited',
        filename = true,
        columns = {
            run_id: 'VARCHAR', case_id: 'VARCHAR', input_digest: 'VARCHAR',
            language: 'VARCHAR', runtime: 'VARCHAR', cwe: 'VARCHAR',
            label: 'VARCHAR', expected_label: 'VARCHAR', decisive: 'BOOLEAN',
            last_gate: 'VARCHAR', rejections: 'STRUCT(gate VARCHAR, rule VARCHAR)[]',
            llm_calls: 'BIGINT', tool_calls: 'BIGINT', seconds: 'DOUBLE'
        }
    )
),
predicted AS (
    SELECT label,
           count(*) AS predicted,
           count(*) FILTER (WHERE label = expected_label) AS correct
    FROM runs
    WHERE label IS NOT NULL
    GROUP BY label
),
expected AS (
    SELECT expected_label AS label, count(*) AS actual
    FROM runs
    WHERE expected_label IS NOT NULL
    GROUP BY expected_label
),
labels AS (
    SELECT label FROM predicted
    UNION
    SELECT label FROM expected
),
metrics AS (
    -- Per-label precision: of the rows given this label, how many were expected to carry it.
    SELECT 'precision' AS metric, l.label,
           coalesce(p.correct, 0)::DOUBLE AS numerator,
           coalesce(p.predicted, 0)::DOUBLE AS denominator
    FROM labels l LEFT JOIN predicted p USING (label)
    UNION ALL
    -- Per-label recall: of the rows expected to carry this label, how many received it.
    SELECT 'recall', l.label,
           coalesce(p.correct, 0)::DOUBLE,
           coalesce(e.actual, 0)::DOUBLE
    FROM labels l LEFT JOIN predicted p USING (label) LEFT JOIN expected e USING (label)
    UNION ALL
    -- Precision of the safe label on known-safe cases: a false safe label is the costliest error.
    SELECT 'safe_precision', $safe_label::VARCHAR,
           count(*) FILTER (WHERE label = $safe_label AND expected_label = $safe_label)::DOUBLE,
           count(*) FILTER (WHERE label = $safe_label)::DOUBLE
    FROM runs
    UNION ALL
    -- Share of known-unsafe cases that received the safe label.
    SELECT 'false_safe_rate', $safe_label::VARCHAR,
           count(*) FILTER (
               WHERE label = $safe_label AND expected_label IS NOT NULL AND expected_label <> $safe_label
           )::DOUBLE,
           count(*) FILTER (WHERE expected_label IS NOT NULL AND expected_label <> $safe_label)::DOUBLE
    FROM runs
    UNION ALL
    SELECT 'decisive_rate', NULL,
           count(*) FILTER (WHERE decisive)::DOUBLE,
           count(*)::DOUBLE
    FROM runs
    UNION ALL
    -- Cost per decisive case, over decisive rows whose usage is known; unknown usage is not zero.
    SELECT 'llm_calls_per_decisive', NULL,
           coalesce(sum(llm_calls) FILTER (WHERE decisive), 0)::DOUBLE,
           count(llm_calls) FILTER (WHERE decisive)::DOUBLE
    FROM runs
    UNION ALL
    SELECT 'tool_calls_per_decisive', NULL,
           coalesce(sum(tool_calls) FILTER (WHERE decisive), 0)::DOUBLE,
           count(tool_calls) FILTER (WHERE decisive)::DOUBLE
    FROM runs
    UNION ALL
    SELECT 'seconds_per_decisive', NULL,
           coalesce(sum(seconds) FILTER (WHERE decisive), 0)::DOUBLE,
           count(seconds) FILTER (WHERE decisive)::DOUBLE
    FROM runs
    UNION ALL
    SELECT 'usage_unknown_rate', NULL,
           count(*) FILTER (WHERE llm_calls IS NULL)::DOUBLE,
           count(*)::DOUBLE
    FROM runs
)
SELECT metric, label, numerator, denominator,
       CASE WHEN denominator > 0 THEN numerator / denominator END AS value
FROM metrics
ORDER BY metric, label NULLS FIRST;
