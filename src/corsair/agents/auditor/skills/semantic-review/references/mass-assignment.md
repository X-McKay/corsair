# Reviewing a mass assignment claim

Use when the controlled value is a body whose keys are applied to an object
(titles such as "Mass assignment", descriptions naming request-body keys
reaching an attribute write). Apply the standing rubric; this says what each
rule checks here.

- R1 mechanism: the hypothesis must name the write loop in the cited `function`,
  the protected attribute, and the editable-field allowlist the source enforces
  or omits.
- R2 differential: the control sets only an ordinarily editable field; the
  exploit differs only in `payload_parameter` and also sets the protected
  attribute through the exact write shown.
- R3 production logic: both go through the production update with the recipe's
  fixed kwargs, not a substitute object.
- R4 disclosure, not echo: the claimed violation is the protected attribute
  being changed/disclosed, not that the body parsed or was echoed.

Reject on the first contradicted rule; a key the object never defines fails R1.
You cannot assert the attribute was set.
