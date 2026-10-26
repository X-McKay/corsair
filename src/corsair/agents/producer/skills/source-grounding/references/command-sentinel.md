# Grounding a command-sentinel pair

Applies when the case recipe `kind` is `python.command_sentinel/1`. The property: the
benign control payload must not create the operator's private sentinel file, and an
input that reaches command or code execution does create it. The sentinel path is fixed
by the operator and shown in the recipe and finding; you never choose or move it.

- The sentinel is the only evidence. You do not assert anything, name the sentinel in a
  return value, or write code: you supply one JSON value for `payload_parameter`, and the
  trusted driver alone checks whether the fixed sentinel file appeared.
- Control payload: a benign, normal value for the callable (an ordinary path, a plain
  setting, an everyday argument) that exercises the reported mechanism without reaching
  execution. It must not create the sentinel and should not raise.
- Exploit payload: a value whose handling, as the source actually processes it, reaches
  command or code execution and creates the sentinel at the recipe's `sentinel_path`.
  Ground it in the observed sink: a shell string passed to `subprocess` with
  `shell=True`, an expression reaching `eval`/`exec`, a path concatenated into a shell
  command. Read the source to confirm the controlled value actually reaches that sink; do
  not assume a sink the code does not have.
- If the callable sanitizes or parameterizes the input so execution cannot be reached, a
  valid pair still has a benign control and a best-effort execution attempt; the kernel
  records that the sentinel was not created. Do not fabricate a sink that is not present.
- Return `no_grounded_candidate` when the source and admissible fixtures cannot ground a
  value that could reach the reported execution sink.
