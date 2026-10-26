# Reviewing a deserialization / code-execution claim

Use when the controlled value is parsed or deserialized (titles such as
"Deserialization of untrusted data" or "Code injection", descriptions naming a
pickle reader or an eval-family call). Apply the standing rubric; this says what
each rule checks here.

- R1 mechanism: the hypothesis must name the exact parse/deserialize call in the
  cited `function` and whether it has a safe branch (literal-only parser, class
  allowlist) the exploit is meant to defeat.
- R2 differential: the control is a value the safe reader accepts as data; the
  exploit differs only in `payload_parameter` and is input the shown call would
  act on but the safe branch should reject.
- R3 production logic: both run through the production reader with the recipe's
  fixed kwargs, not a stand-in.
- R4 disclosure, not echo: the claimed violation is disclosure of the protected
  value, not that parsing succeeded or that input was echoed.

Reject on the first contradicted rule; a plausible-looking payload against the
wrong call still fails R1/R3. You cannot assert the input executed.
