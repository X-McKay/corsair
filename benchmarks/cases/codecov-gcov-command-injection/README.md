# codecov-node gcov command injection (CVE-2020-15123): Jest control and security tests

`corsair.test.js` is a Corsair-written test file for [codecov/codecov-node](https://github.com/codecov/codecov-node), placed at `test/corsair.test.js` as the runner's patch. It is not upstream code. Baseline (vulnerable) `5f6cc62d4f83bf3a75c973868259798814cd231e`, fix `c0711c656686e902af2cd92d6aecc8074de4d83d` ("Switch from execSync to execFileSync"): the gcov command line built from `gcov-root`, `gcov-exec` and `gcov-args`, which `sanitizeVar` only strips of `&`, was run through a shell by `execSync`; the fix runs it with `execFileSync`, so no shell interprets it.

- `corsair_control`: `upload` with `dump`, detection and report search disabled, and an empty scratch directory as `gcov-root` returns the given token and no files; it passes at both commits.
- `corsair_security`: the same call with `gcov-root` carrying `; touch <marker>; true`; the test asserts the marker was not created. At the baseline the shell runs the injected command, so the assertion fails; at the fix nothing is created.

Run image-only with `tests/qualification/node_image_case.py` (SPEC-0057, PLAN-0069): `setup` installs the project's lockfile with `npm ci --ignore-scripts` per commit, `run` drives `JestRunner` offline with ids `test/corsair.test.js::corsair_control` and `test/corsair.test.js::corsair_security`.
