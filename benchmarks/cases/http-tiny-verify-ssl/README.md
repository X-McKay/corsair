# HTTP-Tiny verify_SSL default (CVE-2023-31486) test

Status: run through the TAP runner in the `perl526` image under local Docker only (image evidence, [SPEC-0061](../../../docs/development/specs/SPEC-0061-perl-tap-runner.md)); **not qualified in OpenShell and not admitted as a benchmark case** (no `case.yaml`). Evaluator-only: keep this directory and the expected outcomes outside blind agent inputs.

The [test file](t/corsair_verify_ssl.t) holds exactly two Test::More subtests, `test_control` and `test_security`, for the runner's `t/corsair_verify_ssl.t#test_control` and `#test_security` ids. Its SHA-256 is `3bb2f8332aa0dc5d424369fefc4c62713398889a939ff8d05396fbb416760349`. Place identical bytes at `t/corsair_verify_ssl.t` in both revisions.

| Input | Identity |
| --- | --- |
| Upstream | [Perl-Toolchain-Gang/HTTP-Tiny](https://github.com/Perl-Toolchain-Gang/HTTP-Tiny) |
| Vulnerable source | `7bdf71f5bdb8d97c8554b59e339d4b82fa41954c`, tree `8bac4269140fbc3f6753a4d38c7206f408c8d790` |
| Fixed source | [`77f557ef84698efeb6eed04e4a9704eaf85b741d`](https://github.com/Perl-Toolchain-Gang/HTTP-Tiny/commit/77f557ef84698efeb6eed04e4a9704eaf85b741d), tree `19a4bf065847eede9b6c3bf885bb43516458775d`; its sole parent is the vulnerable commit |
| Native framework | Test::More 1.302073 and Perl 5.26.3 from the image; the checked-in `Makefile.PL` (no Dist::Zilla step) |
| Licensing | Both assertions are copied unchanged from upstream `t/180_verify_SSL.t` at the fixed commit; HTTP-Tiny is distributed under the same terms as Perl 5 (`dist.ini`: `license = Perl_5`) |

The control checks that an explicit `verify_SSL => 0` is honoured; it passes on both revisions. The security test checks that certificates are verified by default; it fails on the vulnerable revision (`got: '0'`, `expected: '1'`, line 23) and passes on the fixed one. Both ran so on 2026-10-13 (PLAN-0066).
