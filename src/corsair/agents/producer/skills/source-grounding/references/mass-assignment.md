# Mass assignment payload pair

Use when the controlled `payload_parameter` is a structured body whose keys are
applied to an object (titles such as "Mass assignment", descriptions naming
request-body keys reaching `setattr` or an attribute update).

What to read in the source:

- Find where the parsed body's keys are written onto the target and whether an
  editable-field allowlist (`EDITABLE_FIELDS`) gates them. Identify the
  sensitive attribute the finding protects (for example an authorization flag)
  and whether the production branch admits it.
- The confinement that matters is exactly which keys the write loop accepts.

Deriving the pair (value of `payload_parameter` only):

- Control: a body setting only an ordinarily editable field, giving the expected
  public result.
- Exploit: a body that, under the exact write the source performs, also sets the
  protected attribute the allowlist is meant to exclude. Base it on the keys the
  loop iterates and assigns; do not assume a field the object does not define.

Do not: change fixed kwargs or the target, bypass by editing the source, or
claim the attribute was observed set. You propose the body value; the verifier
observes any disclosure.
