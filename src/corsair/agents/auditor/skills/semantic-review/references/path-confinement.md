# Reviewing a path-confinement claim

Use when the finding is a path-containment claim (titles such as "Path
traversal" or a description that the callable must not return a file outside its
configured root). Apply the standing rubric; this only says what each rule
checks for this class.

- R1 mechanism: the hypothesis must name the real join/normalization in the
  cited `function` and the containment the source does or omits, not a generic
  "traversal" claim unrelated to the shown code.
- R2 differential: the control names a declared public fixture under the root;
  the exploit differs only in the `payload_parameter` and aims outside the root
  through the callable's own path handling.
- R3 production logic: both payloads go through the production reader with the
  recipe's fixed root/kwargs, not a stand-in opener.
- R4 real violation, not echo: the claimed violation is returning the out-of-root
  private file's content, not echoing the supplied path or matching a marker.

Reject on the first contradicted rule; do not repair the hypothesis into a
different claim. You cannot assert the file was read.
