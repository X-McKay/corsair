# Error and exception exposure payload pair

Use when the finding is that a failure path returns or logs sensitive internal
detail (titles such as "Information exposure through an error message",
descriptions naming a traceback, stack trace, or an error response).

What to read in the source:

- Find the handler and compare its success path with its failure path. Identify
  what the failure path puts into the caller-visible response: a formatted
  exception/traceback that embeds module state (such as a connection string), or
  a fixed generic message.
- Note what input the controlled value must be to reach the failure branch
  rather than the success branch.

Deriving the pair (value of `payload_parameter` only):

- Control: a value that drives the success path, producing the expected public
  result.
- Exploit: a value that triggers the exact failure branch the finding names, so
  the response body the code builds is the detailed one rather than the generic
  one. Ground this in which branch the source takes for that input; the
  disclosure is the internal detail the handler itself writes.

Do not: change fixed kwargs or the handler, assume a message the code does not
build, or paste a real secret. The protected value is unavailable by design.
