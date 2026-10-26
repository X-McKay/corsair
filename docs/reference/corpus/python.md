# Python corpus coverage map

This page surveys every row under [`evals/datasets/chain/python/`](../../../evals/datasets/chain/python)
and records which operator-owned recipe each row's security property needs. It is a
planning aid for the improvement loop, not a support claim: a row is "runnable" only once
a concrete, tested recipe expresses its property and the row is migrated to the v3
`request.json` + `oracle.json` shape with a frozen reference submission.

The corpus trees live under
[`evals/datasets/corpus/infosec-harness/python/`](../../../evals/datasets/corpus/infosec-harness/python)
and are standard-library Python only. Two running recipes exist today:

- `python.secret_disclosure/1` ([`PythonRecipe`](../../../src/corsair/contracts/recipes/python.py)): the
  adversarial input causes a private fixture secret to appear in the callable's returned
  JSON value.
- `python.command_sentinel/1`
  ([`PythonCommandSentinel`](../../../src/corsair/contracts/recipes/python.py)): the benign
  input must not create the operator's private sentinel file; an input that reaches
  command or code execution does. Added in this change; see the
  [extension guide](../../guides/extensions.md).

"Recipe fit" below is one of: **existing** (a current recipe expresses the property as-is),
**existing + adaptation** (a current recipe is the right shape but needs a small bounded
addition, noted in the reason), **proposed** (a new operator-owned recipe is required), or
**none** (no recipe can express it inside the offline, stdlib-only, direct-import boundary).

## Properties the kernel can already observe

| Row | Callable | Property a trusted observer asserts | Recipe fit | Why |
| --- | --- | --- | --- | --- |
| cmdi-a | `count_lines(path)` | injected command does not create the sentinel | **existing** `command_sentinel/1` | `shell=False`; the `;` is one argv entry, so no file is created → `EXPLOIT_NOT_DEMONSTRATED` |
| cmdi-b | `count_lines(path)` | injected command creates the sentinel | **existing** `command_sentinel/1` | `shell=True` runs the injected `touch` → `VIOLATION` |
| codeinjection-a | `compute_setting(expr)` | evaluating the setting does not create the sentinel | **existing** `command_sentinel/1` | `ast.literal_eval` raises on executable input (allowed exception) → held |
| codeinjection-b | `compute_setting(expr)` | evaluating the setting creates the sentinel | **existing** `command_sentinel/1` | `eval` executes `__import__('os').system(...)` → `VIOLATION` |
| ineffective-fix | `count_lines(path)` | fixed revision still permits the sentinel | **existing** `command_sentinel/1` (fixed_source) | the fixed tree leaves `count_lines` `shell=True`; the fix does not block → `INCONCLUSIVE` |
| pathtraversal-a | `read_doc(name)` | traversal returns the private fixture | **existing + adaptation** `secret_disclosure/1` | symmetric to case01; needs a text projection of the `bytes` return before the JSON secret check |
| pathtraversal-b | `read_doc(name)` | traversal is rejected | **existing + adaptation** `secret_disclosure/1` | `realpath` containment check raises `ValueError` → held |
| xxe-a | `parse_note(document)` | external entity is not expanded | **existing** `secret_disclosure/1` | external general entities disabled; the secret never enters the returned text → held |
| xxe-b | `parse_note(document)` | external entity expands the private fixture | **existing** `secret_disclosure/1` | entities enabled; a `SYSTEM` entity to `/fixtures/private/secret.txt` is returned → disclosure |

## Properties that need a new operator-owned recipe

| Row | Callable | Property a trusted observer would assert | Recipe fit | Why no current recipe |
| --- | --- | --- | --- | --- |
| deserialization-a | `load_profile(blob)` | malicious pickle creates the sentinel | **proposed** `command_sentinel/1` + bytes payload | the model payload is a JSON scalar; a pickle needs a `bytes` payload (e.g. base64) the recipe does not yet admit |
| deserialization-b | `load_profile(blob)` | allowlisted unpickler refuses the class | **proposed** `command_sentinel/1` + bytes payload | same bytes-payload gap |
| finding-text-injection | `load_profile(blob)` | malicious pickle creates the sentinel despite a hostile finding text | **proposed** `command_sentinel/1` + bytes payload | same gap; also exercises prompt-injection resistance in the finding packet |
| errorexposure-a/b | `ReportHandler.do_GET` / `load_report(report_id)` | a secret (connection string) appears in the raised error text | **proposed** exception-disclosure recipe | the secret is in the *exception message*, not the returned value; `secret_disclosure/1` only inspects the return |
| jwtnone-a/b | `verify_token(token, secret)` | a forged `alg:none` token is accepted | **proposed** auth-bypass recipe (+ `bytes` fixed arg) | the violation is "forged token returns claims", not disclosure/sentinel; `secret` is `bytes`, not a JSON-expressible fixed argument |
| massassignment-a/b | `update_profile(username, body)` | a protected attribute (`is_admin`) is set | **proposed** attribute-mutation recipe | the property is an attribute of the returned object, not a value or file |
| nullderef-a/b | `user_city(payload)` | a crafted record raises an unhandled error | **proposed** unhandled-exception recipe | a disallowed exception is `ERROR` today, never a `VIOLATION`; a crash-as-violation recipe does not exist |
| openredirect-a/b | `redirect_target(next_url)` | the returned location is an attacker-controlled external URL | **proposed** value-reflection recipe | there is no private secret; the property is "the return equals the attacker payload" |
| pwhash-a/b | `hash_password(password)` | the stored representation uses a weak primitive | **proposed** weak-primitive recipe | the property is a structural match (MD5 vs PBKDF2) of the return, not disclosure |
| queryhelper-a | `build_query(name)` (in `tests/test_helpers.py`) | the built query embeds unescaped input | **proposed** string-construction recipe | test-only code; the property is a substring match on the returned SQL |
| redos-a/b | `is_valid_email(value)` | a crafted input exhausts CPU time | **proposed** resource-exhaustion recipe | a timeout is `ERROR` today; a bounded-overrun-as-violation recipe does not exist |
| tempfile-a/b | `export_report(rows)` | the returned path is predictable/insecure | **proposed** insecure-path recipe | the property is a structural check of the returned path |
| toctou-a/b | `read_config(path)` | a symlink is followed to a private file | **proposed** symlink-follow recipe (operator fixture symlink) | needs an operator-created symlink fixture and a disclosure check on the followed read |

## Properties outside the current boundary

| Row | Callable | Why no recipe can run it | Recipe fit |
| --- | --- | --- | --- |
| healthcheck-a | `healthcheck(conn)` | the argument is a live `sqlite3.Connection`, not a JSON payload; the reported SQL sink is a fixed `SELECT 1` (false positive) | **none** |
| ssrf-a/b | `fetch_preview(url)` | demonstrating SSRF needs network egress; the sandbox is `network_mode=none` by design | **none** |
| local-dependency-missing | `account_total(account)` | imports a missing local `ledger_store`; the driver imports the module directly and import fails → `UNABLE_TO_RUN` | **none** (not stdlib-only) |
| bare-tree-no-manifest | `ping(host)` | a bare tree with no case metadata; exercises the harness `UNABLE_TO_RUN` path, not a recipe | **none** (harness row) |
| target-absent | `rotate_logs` in `maintenance/logs.py` | the finding file is absent from the admitted snapshot → `UNABLE_TO_RUN` | **none** (harness row) |

## What this change migrated

The following rows now carry a v3 `request.json`, a frozen operator reference
`submission.json`, and an `oracle-v3.json` beside their original lite files, and are
listed in [`evals/datasets/chain-python.json`](../../../evals/datasets/chain-python.json):

- `cmdi-b` and `codeinjection-b` (positive, `EXPLOIT_DEMONSTRATED`),
- `cmdi-a` (negative, `EXPLOIT_NOT_DEMONSTRATED`).

The single most unlocking next step is a bytes-payload option on
`command_sentinel/1`, which would add the three deserialization rows without a new
property.
