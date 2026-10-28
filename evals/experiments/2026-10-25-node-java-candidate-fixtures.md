# Node and Java candidate fixture packets

Date: 2026-10-25. This is an AI-authored candidate-fixture design record pending human review. It records frozen source, packet, and oracle construction only. It is not a live-model experiment, a target execution result, Docker or Temporal evidence, a qualification record, or a language-support claim.

The three new manifests are deliberately separate:

| Manifest | Cohort boundary | Raw SHA-256 |
| --- | --- | --- |
| `datasets/node-java-producer.json` | Exact isolated-producer payload diagnostic | `10fe1f149f4702ec38db37b384988c6bf9380bfd0b4e110b74cfdcc6470fd2a1` |
| `datasets/node-java-auditor.json` | Exact isolated-auditor semantic-review diagnostic | `80733a7451db9922cad22abe2dcc2d8fc96e48582f34712dc6cbd0585fba95e9` |
| `datasets/node-java-assessments.json` | External composed-outcome expectations | `6451150854128cd48e4c0f6f1eb7ee58c38fbccd42c34d0cd132370e93fef2ef` |

Each of `node01`, `node02`, `java01`, and `java02` is in the `candidate` split. The Node pair uses canonical `javascript.secret_disclosure/1` recipes with the explicit ESM named export `read(baseRoot, payload)`, `fixed_args` of `[/fixtures/allowed]`, and `payload_index` 1. The Java pair uses canonical `java.secret_disclosure/1` recipes with JDK-only public class `Gate` in `Gate.java`, public static `String read(String baseRoot, String payload)`, the same positional configuration, and the normal-path `Files.readString` read. The Java source trees contain no build files; the Node source trees contain no package metadata or dependency declaration.

For each language, the `01` case is a vulnerable returned-file reader and the `02` case normalizes the candidate then returns `blocked` from an explicit containment guard for the declared parent traversal. All cases fix the public `hello.txt` fixture to `hello`, use `../private/secret.txt` as the reference candidate, and omit every private fixture value. The declared finding line is the returned-file read for vulnerable cases or the containment condition for guarded cases. Those lines are reached on both healthy control and adversarial roles; none names dead code.

Every case has a standalone `reference.json` canonical `Submission` with revision 1 and no parent revision. Its hypothesis is source-grounded and conditional. The guarded packet specifically acknowledges that the traversal should take the guard and return `blocked`, rather than asserting an unsupported bypass. Its auditor oracle remains external and expects `ACCEPT`: a semantic review can accept a valid paired probe without predicting that the adversarial candidate succeeds.

Producer requests and auditor packets are separate frozen documents with independently listed exact digests in their respective manifests. Assessment entries use the canonical `corsair.assessment-oracle/1` shape, separate from both source trees and model/workflow packets. The external expected outcomes are `DEMONSTRATED` for the vulnerable readers and `NOT_DEMONSTRATED` for the guarded readers, subject to actual trusted evidence and scorer validation if a composed cohort is later run.

The source identities were derived by the canonical `snapshot_source` helper only, without host import, compilation, dependency resolution, or execution of a target. Per-case snapshot, packet, and manifest identities plus offline-test commands are retained in the private construction receipt at `.work/node-java-evolution-20261025/results/fixtures.md`.

This candidate cohort is unpromoted and is not independently calibrated or evidence of broad Node, Java, language, framework, security, negative-clearance, model-accuracy, or production behavior. Any later isolated or composed run must retain its full denominator, actual configuration identities, operational failures, and separately human-reviewed promotion decision.
