# Reviewing an error/exception exposure claim

Use when the finding is that a failure path leaks internal detail (titles such
as "Information exposure through an error message", descriptions naming a
traceback or error response). Apply the standing rubric; this says what each
rule checks here.

- R1 mechanism: the hypothesis must name the cited handler's failure branch and
  the internal detail it writes to the caller-visible response, contrasted with
  its success branch.
- R2 differential: the control drives the success path; the exploit differs only
  in `payload_parameter` and forces the exact failure branch the finding names.
- R3 production logic: both go through the production handler with the recipe's
  fixed kwargs, not a reconstructed response.
- R4 disclosure, not echo: the claimed violation is the handler disclosing its
  own internal detail, not echoing the attacker's input or merely returning an
  error status.

Reject on the first contradicted rule; do not assume a message the code does not
build. You cannot assert the response was observed.
