# Command and argument injection payload pair

Use when the controlled `payload_parameter` reaches a process-spawning call
(titles such as "OS command injection" or descriptions naming `subprocess`, a
shell, or an argument passed to an external program).

What to read in the source:

- Find the spawn site and how the controlled value is placed: concatenated into
  a single shell string (`shell=True`), or passed as one element of an argument
  list (`shell=False`). The seam that matters is which of these the production
  `function` uses.
- Confinement to look for: an allowlist of commands, a rejection of shell
  metacharacters, or argument separators that stop the value from becoming a new
  token. The control branch stays within it.

Deriving the pair (value of `payload_parameter` only):

- Control: an ordinary operand the call accepts (for example a declared public
  fixture name), producing the expected public result.
- Exploit: a value that, given exactly how the source passes it, changes what
  the process does — a second token or option when the value is concatenated
  into a shell string, or an option the listed program interprets when it is a
  list element. Keep it tied to the observed call shape; do not assume a shell
  that `shell=False` never invokes.

Do not: change `fixed_kwargs`, invent a different sink, or assert the command
ran. You propose the value; the trusted verifier observes any disclosure.
