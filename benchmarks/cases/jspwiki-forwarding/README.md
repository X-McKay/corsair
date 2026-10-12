# JSPWiki forwarding test draft

Status: independently reviewed source design; **not compiled, discovered, executed or qualified**. This evaluator-only artifact belongs to [PLAN-0021](../../../docs/development/plans/PLAN-0021-multilingual-corpus-admission.md). Keep this directory, source labels and expected results outside blind agent inputs. It adds no case-specific core logic or production runner.

The [test file](BenchmarkWikiServletForwardingTest.java) contains exactly two native JUnit Jupiter methods. Its frozen SHA256 is `6ebf62443a54fc98b0d3f3680d4aa0fde239888db10bc8b5158026faa369b95d`. Place identical bytes at `jspwiki-main/src/test/java/org/apache/wiki/BenchmarkWikiServletForwardingTest.java` in each admitted source variant. A later correction requires a new freeze and paired runs; never change only one variant.

| Input | Verified identity |
| --- | --- |
| Upstream | [Apache JSPWiki](https://github.com/apache/jspwiki) |
| Candidate vulnerable source | `f140a2a4371735ad24d04a1d78c6e1d9ceaed76f`, tree `d8f10520bc2f482b42542963ff9a837bb61e8f4f` |
| Fixed source | [`88d89d6523802c044cfcb7930cba40d8eeb21da2`](https://github.com/apache/jspwiki/commit/88d89d6523802c044cfcb7930cba40d8eeb21da2), tree `e40f3fe60cdfe206fafa0fd7c8dfc80cfeaabf8f` |
| Relationship | Fixed commit has the sole parent above; complete tree inventories verified |
| Native framework | JUnit Jupiter 5.4.0, Surefire 2.22.0, Stripes 1.7.0-async-beta; unchanged upstream POMs |
| Licensing | Unchanged upstream [LICENSE](LICENSE) blob `666473f498f4488e1c26e33a4bd8522bcfc178ee` and [NOTICE](NOTICE) blob `2f7a392b9af9bbe93d4fce5f649e833118d82945`; test adapted from upstream servlet-test setup |

The benign method checks a non-null forwarded ordinary-page request and its preserved page parameter, without asserting the fixed-only dispatcher target. The security method checks that an inert web-root readme request routes to the normal wiki endpoint. Both call the real `WikiServlet.doGet`; Stripes supplies only the servlet request/context and recording dispatcher. The pinned Stripes source confirms that the constructor does not set path info, so the test explicitly sets it.

This observes the application's **dispatcher choice**. The mock dispatcher does not execute a JSP or open the requested resource; neither successful assertions nor a parent failure would prove deployed file disclosure. An intended vulnerable assertion failure needs the actual non-null asset-targeting forward URL and a passing benign control. Setup failure, null output, denial, skipped discovery or unknown execution is inconclusive. `WikiEngine` initialization and shared cache shutdown must also work across the two methods and repeated fresh runs.

## Remaining admission and execution

The existing Java 17/Maven image is qualified only with a different synthetic dependency cache. Do not run this draft using that qualification alone. First admit a separate immutable historical dependency/plugin closure and Java 17 compatibility, the concrete nonempty test transfer recipe and bounded native report collection.

Complete source acquisition and local capture are now verified separately: a new private complete bare repository passed strict native object checks, and existing `GitSource` captured both full trees once under explicit limits (2048 files, 4MiB/file, 20MiB total, 60s wall, 512MiB memory, 30s CPU). Parent/fix capture took6.052/6.168s. Fresh artifact-store readback and root review verified all3447 file references. Manifest SHA256 values are `ddb4639c7558b8b8cbf7b4fa78e06a523fb7917540a341749d27dd982f947774` and `e9e89a5a082a415db0044d1f3a4a591e28ee8504fce9fcd0c80d837d736ec64f`. This is local immutable capture, not admission of a full-project upload, dependency cache or execution. The earlier shallow research clone remains untouched.

After fresh storage/kernel/CNI/gateway admission and the concrete recipe gate, use the pinned JUnit Platform 1.4.0 `Launcher.discover` API to prove exactly the two method identities without executing their bodies. Discovery still loads untrusted classes and needs confinement. Then run native Surefire on each source three times in fresh sandboxes, retaining complete target XML, both forward-URL witnesses, source/test/cache/runtime/command identities, individual budgets and identity-checked cleanup. Require exactly two executed methods and zero skips; a reactor selector flag cannot establish this.

Expected outcomes are evaluator hypotheses pending execution: benign passes on both, security fails for the candidate vulnerable source and passes for fixed source. There are currently **zero real-case executions**. Private source, pinned Stripes source-JAR, draft review and proposed discovery/recipe evidence are retained under `.runs/post-pr21-qualification-20261012/`; they are not qualification receipts or distributable raw logs.
