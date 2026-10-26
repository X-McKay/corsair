# SSRF and host allowlist payload pair

Use when the controlled `payload_parameter` is a URL or host that the callable
fetches (titles such as "Server-side request forgery" or descriptions naming
`urlopen`, a request client, or a link preview).

What to read in the source:

- Find where the value becomes a network destination and whether the code parses
  it first. Note any confinement: a scheme check, a host allowlist
  (`ALLOWED_HOSTS`), or none.
- Identify how the host is extracted, because the control branch must present a
  destination that passes exactly that extraction.

Deriving the pair (value of `payload_parameter` only):

- Control: a URL whose scheme and host satisfy the code's allowlist/parse, so the
  expected public behavior is a normal fetch of a declared public resource.
- Exploit: a destination that the code's own parsing and allowlist treat as
  permitted or unparsed yet points at the private/internal resource the finding
  protects. Base it on how the source parses and compares the host; do not assume
  a check the source does not perform.

Do not: alter fixed kwargs, substitute a different client, add credentials, or
claim a response was received. The private fixture value stays unavailable.
