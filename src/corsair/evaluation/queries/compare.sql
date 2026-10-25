-- Compare two runs over newline-delimited run-record rows (see README.md for the row shape).
-- Parameters: $baseline and $candidate (file globs, one row per case on each side).
-- Output: one row per case. `comparable` is false when the case is missing on either side or
-- the input digests differ; the reader refuses the comparison if any row is not comparable.
WITH baseline AS (
    SELECT *
    FROM read_json(
        $baseline,
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
candidate AS (
    SELECT *
    FROM read_json(
        $candidate,
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
)
SELECT coalesce(b.case_id, c.case_id) AS case_id,
       b.input_digest AS baseline_digest,
       c.input_digest AS candidate_digest,
       coalesce(b.input_digest = c.input_digest, false) AS comparable,
       b.label AS baseline_label,
       c.label AS candidate_label,
       coalesce(b.expected_label, c.expected_label) AS expected_label,
       b.decisive AS baseline_decisive,
       c.decisive AS candidate_decisive,
       c.llm_calls - b.llm_calls AS llm_calls_delta,
       c.tool_calls - b.tool_calls AS tool_calls_delta,
       c.seconds - b.seconds AS seconds_delta
FROM baseline b
FULL OUTER JOIN candidate c ON b.case_id = c.case_id
ORDER BY case_id;
