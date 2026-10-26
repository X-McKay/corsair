# Reviewing a command-sentinel submission

Applies when the recipe `kind` is `python.command_sentinel/1`. The trusted violation
condition is creation of the operator's `sentinel_path` file, which only genuine command
or code execution reached by the payload can cause. You assess semantic coherence only;
you never assert that execution happened or that the sentinel appeared.

- R1: the hypothesis must describe a real execution sink in the source (a `subprocess`
  call with `shell=True`, an `eval`/`exec`, a shell string built from the controlled
  value), not an unrelated mechanism.
- R2: the `control_payload` is a benign value that should not reach execution; the
  `exploit_payload` differs in the caller-controlled `payload_parameter` and plausibly
  reaches the sink.
- R4 real violation, not echo: a coherent claim targets the sentinel's creation via execution. Reject a claim
  whose "violation" is merely that the callable returned, echoed the payload, or that a
  marker string matched; those are not the sentinel condition. Do not reward a payload
  that would create the file by a path the source does not actually execute.
- You cannot confirm the sentinel was created; that is the trusted driver's finding.
  Acceptance only says the attempt is a coherent test of the reported execution sink.
