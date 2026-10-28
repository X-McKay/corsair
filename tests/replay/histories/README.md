# Pre-assessment replay fixtures

Recorded from actual Temporal execution at base revision
`6beebbcb6b3791ec4d5b144bebe245f3c73a23c5`, before the outcome evolution.
These are **scripted-activity, genuine Temporal** histories, not live-model or Docker
qualification. The positive and held pair each completed prepare, produce, evidence,
audit and record. They contain no model calls, target code, private fixture values,
credentials, checkout paths or native target evidence. Worker identity strings were
replaced with `corsair-test-worker`; event order, payloads and command facts are intact.

Both lack the `assessment-outcomes-v1` marker and return `corsair.result/1`.
The current SDK Replayer must not schedule new activities or alter old result payloads.

- `pre-assessment-positive.json`: SHA-256 `3a7197d52054b85f13650563c81cfe09df77185c3c44c12f75698652d52a53ff`.
- `pre-assessment-held.json`: SHA-256 `1245367ffa06b97368d35f028a2c90decbfd7a0b4cc2f1c096422eae08459cb3`.
