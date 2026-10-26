# Deserialization and code-execution payload pair

Use when the controlled `payload_parameter` is parsed or deserialized by a
mechanism that can run or construct objects (titles such as "Deserialization of
untrusted data" or "Code injection", descriptions naming `pickle`, an
`eval`-family call, or restoring a cached object).

What to read in the source:

- Find the parse/deserialize call and whether it is a safe reader or one with
  side effects: a literal-only parser versus a general evaluator, or an
  unrestricted unpickler versus one with a class allowlist (`find_class`).
- The confinement that matters is exactly which inputs the safe branch admits.

Deriving the pair (value of `payload_parameter` only):

- Control: a well-formed value the production reader accepts as plain data,
  giving the expected public result.
- Exploit: a value that is valid input to the exact call the source uses but
  that the safe branch is meant to reject — a construct the general evaluator or
  unrestricted reader would act on that a literal-only or allowlisted reader
  would not. Keep it a description of the input shape, grounded in the call; do
  not supply or require the private fixture's content.

Do not: change the sink or fixed kwargs, embed a real secret, or assert the
input was executed. You propose the value; the verifier observes the effect.
