# Unit observation of SQL query construction

This reviewed fixture demonstrates the common unit-test boundary: call the real application function and inject a recording dependency through its existing argument. `RecordingDatabase` records query text and parameter values and returns a deterministic result. It connects to no database.

`test_queries.py` contains exactly two issue-validation tests. The benign control establishes that the target calls the dependency with the expected benign query and returns its result. The security regression requires hostile input to remain a bound parameter while the query structure stays fixed. The same pair runs against `unsafe/queries.py` and `safe/queries.py`: control passes on both, security fails for concatenation and passes for parameterization.

The repository evaluator `test_reviewed_native_query_construction_pair_requires_no_database` copies only these reviewed bytes into a temporary workspace, executes native pytest, and checks its JUnit outcomes. This establishes query-construction behavior in Python. It does not establish database-engine semantics, exploitability against a real database, or live qualification of other languages or frameworks. Their native test seams can use the same observation contract; engine-specific properties require suitable integration evidence.
