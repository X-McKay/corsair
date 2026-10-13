# bestzip command injection (CVE-2020-7730): Jest control and security tests

`corsair.spec.js` is a Corsair-written test file for [nfriedly/node-bestzip](https://github.com/nfriedly/node-bestzip), placed at `test/corsair.spec.js` as the runner's patch. It is not upstream code. Baseline (vulnerable) `fcea252e52b6078eff6caf5531bd32c53fccb59f`, fix `45d4a901478c6a8f396c8b959dd6cf8fd3f955b6` ("prevent shell command injection": `cp.exec` of a built `zip` command line replaced by `cp.spawn` with an argument list).

- `corsair_control`: the pure-JavaScript `nodeZip` path writes a non-empty archive of `test/fixtures/file.txt`; it passes at both commits.
- `corsair_security`: `nativeZip` with a destination carrying `; touch <marker>; true`; the test asserts the marker file was not created. At the baseline the shell runs the injected command (the `zip` binary itself need not exist), so the assertion fails; at the fix `spawn` passes the destination as one argument and nothing is created.

Run image-only with `tests/qualification/node_image_case.py` (SPEC-0057, PLAN-0069): `setup` installs the project's lockfile with `npm ci --ignore-scripts` per commit, `run` drives `JestRunner` offline with ids `test/corsair.spec.js::corsair_control` and `test/corsair.spec.js::corsair_security`.
