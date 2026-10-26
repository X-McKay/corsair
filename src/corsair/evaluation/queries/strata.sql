-- Scorecard strata over newline-delimited run-record rows (see README.md for the row shape).
-- Parameters: $runs (file glob), $safe_label.
-- Output: one row per (dimension, stratum) for language, runtime, cwe and last_gate.
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
cuts AS (
    SELECT 'language' AS dimension, language AS stratum, * FROM runs
    UNION ALL
    SELECT 'runtime', runtime, * FROM runs
    UNION ALL
    SELECT 'cwe', cwe, * FROM runs
    UNION ALL
    SELECT 'last_gate', last_gate, * FROM runs
)
SELECT dimension,
       stratum,
       count(*) AS runs,
       count(*) FILTER (WHERE decisive) AS decisive,
       count(*) FILTER (WHERE label = expected_label) AS correct,
       count(*) FILTER (
           WHERE label = $safe_label AND expected_label IS NOT NULL AND expected_label <> $safe_label
       ) AS false_safe,
       sum(llm_calls) AS llm_calls,
       sum(tool_calls) AS tool_calls,
       sum(seconds) AS seconds,
       count(*) FILTER (WHERE llm_calls IS NULL) AS usage_unknown
FROM cuts
GROUP BY dimension, stratum
ORDER BY dimension, stratum NULLS LAST;
