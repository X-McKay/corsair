-- Rejection ledger over newline-delimited run-record rows (see README.md for the row shape).
-- Parameters: $runs (file glob).
-- Output: rejections grouped by gate and audit rule; rows without rejections contribute nothing.
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
)
SELECT rejection.gate AS gate,
       rejection.rule AS rule,
       count(*) AS rejections,
       count(DISTINCT (run_id, case_id)) AS runs
FROM runs, unnest(runs.rejections) AS t(rejection)
GROUP BY rejection.gate, rejection.rule
ORDER BY rejections DESC, gate NULLS LAST, rule NULLS LAST;
