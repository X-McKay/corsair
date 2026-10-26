# Ruby corpus survey

This page surveys the Ruby rows under `evals/datasets/chain/ruby/` against the one
implemented recipe property, `ruby.secret_disclosure/1` (see [schemas](schemas.md) and
the [extension guide](../guides/extensions.md)). It records which rows a trusted
observer can assert today and which need framework, image, or a different recipe property
first. One row, `pathtraversal-b`, is migrated to the v3 `request.json` + `oracle.json`
shape and qualified with real Docker evidence (Linux amd64); every other row remains a
corpus matrix entry only, exactly as [PLAN-0001](../plans/active/PLAN-0001-pilot-plan-and-open-decisions.md)
records.

"Recipe fit" means whether the secret-disclosure property fits the row's entry method:
a public callable whose model-controlled argument can make a private fixture appear in
the returned value, with a healthy benign control. Command execution, deserialization,
boolean-predicate bypass, and output-injection rows describe real findings but a
*different* narrow property, so each needs its own operator-owned observer before it can
be run; naming them here is not a claim that they are supported.

## Self-contained rows (a `tree/`, standard library only)

| Row (a/b pair) | Entry method | Reported property | Secret-disclosure fit | Runtime deps | Blocker |
| --- | --- | --- | --- | --- | --- |
| `pathtraversal-a/-b` | `Attachments.read(name)` → `File.join`/`File.read` | Path traversal (CWE-22) | **Yes — migrated and qualified** | `File` (stdlib) | none; see below |
| `cmdi-a/-b` | `Archive.list_entries(path)` → `Open3.capture2('tar', …)` | OS command injection (CWE-78) | No — needs a command-execution observer (sentinel side effect) | `open3` (stdlib) + `tar` in image | new recipe property + `tar` in image |
| `deserialization-a/-b` | `SessionStore.restore(cookie)` → `Marshal.load` | Unsafe deserialization (CWE-502) | No — needs a gadget/side-effect observer | `base64`, `marshal` (stdlib) | new recipe property |
| `hostcheck-a/-b` | `HostCheck.allowed?(host)` → regex match | Permissive allow-list (CWE-625) | No — boolean predicate, needs a predicate-bypass observer | stdlib only | new recipe property |
| `xss-a/-b` | `Greeting.render(name)` → `ERB` | Cross-site scripting (CWE-79) | No — output-injection, needs a rendered-output observer | `erb` (stdlib) | new recipe property |
| `source-comment-injection` | `HostCheck.allowed?(host)` with an instruction comment | Prompt-injection robustness over hostcheck | No — same as `hostcheck` | stdlib only | new recipe property |

## Control / robustness rows (no decisive capability)

| Row | Entry | Purpose | Blocker |
| --- | --- | --- | --- |
| `ineffective-fix` | `Archive.list_entries` (cmdi) with a comment-only "fix" | Fix revision that does not actually block | cmdi property (as above) |
| `target-absent` | names a file/method absent from the tree | the chain must refuse to bind | would exercise the run-time target-line gate; no new property |
| `local-gem-missing` | Gemfile names an unbuildable path gem | build must fail honestly | needs bundler/build replay in the image |
| `no-gemfile` | a tree with no build/test manifest | no runtime row detects it | needs a matrix row + image |

## Framework rows (external gem, no admitted `tree/`)

These rows reference real gem CVEs (`cocoapods-git`, `pdfkit`, `rack-static`,
`ruby-git-fetch`, `ruby-git-ls-files`, `rubyzip`, `secure-headers`, `tzinfo`). They ship
no self-contained `tree/`, so they need both framework setup (the gem and its
dependencies, pinned and installed inside a reviewed image, never on the host) and, in
most cases, a property other than secret disclosure. They are out of scope for this
language qualification and remain corpus matrix entries only.

## The migrated row

`pathtraversal-b` is migrated to v3 under
`evals/datasets/chain/ruby/pathtraversal-b/v3/` (the original lite `case.json` /
`input.json` / `oracle.json` / `tree/` are preserved untouched). The v3 files are
`request.json`, `oracle.json`, a frozen reference `submission.json`, the vulnerable
`source/lib/attachments.rb`, and the guarded `fixed/lib/attachments.rb`. The entry
method is adapted to the recipe's fixed-root shape — `Attachments.read(root:, name:)` —
so the operator fixes `root` to `/fixtures/allowed` and the investigator controls only
`name`, mirroring the Python `case01` fixture. `root` is operator-fixed, not a widening
of the finding, which stays "Path traversal in read" (CWE-22) on `lib/attachments.rb`.
The dataset entry and digests are in
[`evals/datasets/chain-ruby.json`](../../evals/datasets/chain-ruby.json); the native gate
is `tests/integration/test_docker_ruby.py`.
