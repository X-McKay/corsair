# Reviewing an SSRF / host-allowlist claim

Use when the controlled value is a URL or host the callable fetches (titles such
as "Server-side request forgery", descriptions naming a request client or
allowlist). Apply the standing rubric; this says what each rule checks here.

- R1 mechanism: the hypothesis must match how the cited `function` parses the
  destination and the allowlist/scheme check it does or omits, not a generic SSRF
  claim.
- R2 differential: the control is a destination the code admits; the exploit
  differs only in `payload_parameter` and reaches the protected destination
  through the source's own parsing/comparison.
- R3 production logic: both go through the production fetch with the recipe's
  fixed kwargs, not a substituted client.
- R4 disclosure, not echo: the claimed violation is disclosure of the protected
  resource, not that a request was made or that the URL was echoed back.

Reject on the first contradicted rule; do not invent a check the source lacks or
repair an unrelated hypothesis. You cannot assert a response was received.
