# ISSUE-0012: typed producer decision remains unpromoted

The `corsair.producer-decision/1` native Pydantic contract and scripted ADK/Temporal consumers are implemented, but the supplied model/recipe configuration has not passed its live promotion gates. Keep the feature PR in draft; a valid schema is not proof of a good candidate.

The unchanged expanded producer freeze returned nine structurally valid decisions: six proposals and three abstentions. The original exact pass predicate scored **3/9**, with zero isolated operational failures. The separately evaluated auditor scored **12/12**. These are small diagnostic fixtures, not population accuracy estimates or qualified baselines.

One actual frozen live batch completed and its existing receipts were recovered after the local command handle disappeared; it was not resubmitted. It scored **0/3**: case01 and case03 ended with explicit `no_grounded_candidate` and no native observation; case02 retained `provider_permanent` and `ERROR`. No positive evidence or forbidden security label was manufactured. Missing cost remains unknown. The provider-error classification does not establish a server, schema or model root cause.

That batch preceded final capability/intent-identity hardening. The final full live chain remains unqualified; native conformance tests do not replace this gate. A follow-up must investigate source grounding and the explicit error, evaluate producer/auditor separately against frozen cases, then qualify the final provider/recipe/capability identity with a fresh bounded composed run. Do not rewrite existing oracles or interpret alternative payloads as valid exploits without trusted native evidence.
