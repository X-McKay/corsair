# Path confinement payload pair

Use when the finding is a path-containment claim: a reader joins the
caller-controlled `payload_parameter` to a fixed root and must not return a file
outside it (titles such as "Path traversal", "Document path validation", or a
description that says the callable must not disclose a file outside its
configured root).

What to read in the source:

- Find the `function` and the line where the controlled value is combined with
  the fixed root (`os.path.join`, `pathlib` joins, string concatenation) and how
  the result is opened.
- Note any confinement the code performs before opening: a `realpath`/`resolve`
  then a prefix check, a rejection of separators, or none at all. The control
  branch you keep must stay inside that logic.

Deriving the pair (value of `payload_parameter` only, never the fixed kwargs):

- Control: a name of one declared public fixture, phrased the way the callable
  expects it (the normalized relative name under the root, or the declared
  absolute path when the callable accepts absolute paths). The expected public
  result is the fixture's declared content.
- Exploit: a relative reference that, after the callable's own join and
  normalization, resolves to the out-of-root private fixture rather than a file
  under the root. Ground it in the join/normalization the source actually does;
  do not add separators, encodings, or null bytes the source never decodes.

Do not: invent directories, supply the private fixture's value, change the root
or fixtures, or claim the file was read. The private value is unavailable by
design.
