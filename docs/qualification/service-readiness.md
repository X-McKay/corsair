# Initial Service readiness qualification

Date: 2026-10-11. Outcome: **qualified for bounded fixture Service admission on two fresh clusters with confirmed cleanup**. The ordinary-pod fixture correction resolves [ISSUE-0003](../development/issues/ISSUE-0003-service-control-readiness.md). This record supplements the [original network qualification](network-platform.md); it does not expand the OpenShell or application qualification envelope.

## Diagnosis against the frozen baseline

Base/source cc97b88204b92fd7e9e8621a34d9abeeba9da08c matched the published open draft PR #4. The prior failing native requests and six failed-fixture UID cleanup receipts were read. Historical curl 7 and curl 28 requests followed successful direct PodIP controls and preceded the affected policy. Earlier diagnostic fixtures and later passing suites did not diagnose those failures. All original attempts remain retained.

On a fresh owned node, `.runs/readiness-baseline-001/` captured the unchanged fixture with concurrent native EndpointSlice samples and read-only node `iptables-save -c` observations. Fixture 1 passed; fixture 2 reproduced the Service GET refusal after direct PodIP GET/POST succeeded:

| Observation, UTC | Actual evidence |
| --- | --- |
| 15:21:30.645 | EndpointSlice first observed Ready/serving for the original echo Pod IP 192.168.20.8 and UID |
| 15:21:31.217 | Strict initial Service GET to 10.96.53.148 failed with curl 7/status 000; `command-0042.json` |
| 15:21:31.406 | Separate diagnostic GET also failed with curl 7/status 000; `command-0044.json` |
| 15:21:31.450 / 31.552 | Native no-endpoints REJECT rule counters increased to 1 then 2 packets |
| 15:21:31.655 | First sampled Service/DNAT route to the original echo Pod; REJECT gone |
| 15:21:31.768 | Fresh diagnostic Service GET succeeded; `command-0045.json` |

Sampling timestamps bound the observed transitions; they do not provide exact controller or proxy event delivery times. The producing layer in this reproduction is asynchronous kube-proxy rule programming after EndpointSlice readiness. Actual proxy config uses iptables/minSyncPeriod 1s. Selected immutable Kubernetes v1.35.8 [proxier source](https://github.com/kubernetes/kubernetes/blob/v1.35.8/pkg/proxy/iptables/proxier.go) emits the observed no-endpoints reject rule and schedules synchronization separately from EndpointSlice updates. Native controller/proxy logs and resource facts accompany request receipts. Actual echo logs contain the successful PodIP/Service markers and exclude both refused-request markers; `.runs/readiness-resume/baseline-audit.json` reconciles those observations. The historical curl 28 failure is individually unattributed; this reproduction does not retroactively diagnose every earlier failed request or establish a Calico defect.

Both diagnostic samplers were reaped and both namespaces deleted only after original UID comparison: corsair-net-07c05793290d / 4d19409c-2730-4dc9-b4b2-2a58cce109ba and corsair-net-405b56cb4ffa / fb323741-2fa2-4eb3-96ea-ccd81dc9e995. Original baseline source hashes and later correction hashes are retained separately.

## Bounded correction

The existing server HTTP readiness probe stays unchanged. After Pod Ready, the trusted fixture now observes the Service-owned EndpointSlice, requires its original Pod UID/IP, TCP/5678 and Ready/nonterminating condition, then requires exact HTTP 200/body and server marker coverage from both probe Pods via the Service. Native kubectl and the existing digest-pinned curl supply these observations. EndpointSlice readiness did not acknowledge proxy programming in the reproduction, so actual fixture traffic is required.

A separate 30-second setup budget retains every endpoint observation and connection attempt in `service-readiness.json` and native command receipts. The setup loop retries only completed curl 7/28 requests with status 000. Wrong output, other errors, unknown delivery, stale endpoint identities or budget exhaustion block admission; cleanup still runs. Successful setup requires both probes in the same observation round. Setup attempts never count as policy controls or denials. Fresh strict GET/POST controls on PodIP and Service, positive log coverage, three denied trials per route/method, rollback and all timeout/deny criteria are unchanged. No pins, policy, TLS, kernel or node configuration changed. Privileged rule inspection was diagnostic only and is absent from the corrected qualification fixture.

## Validation and evidence

Before live work, the existing 18 offline guards passed in 0.07s; after the initial correction, 28 guards passed in 0.09s; final review guards bring the suite to 30 passing checks in 0.09s. Twelve new fail-closed guards cover transient retention with strict-control separation, missing/empty endpoints, replaced identities, unexpected exec/HTTP output, permanent connection failures, unknown delivery, unexpected existing policies and absent server marker coverage. These mocks test fixture admission decisions, not network enforcement.

The pre-review corrected suite `.runs/readiness-network-001/` passed all three tests in 155.30s on node UID 07cd29ad-ce37-4a1c-8460-dec6c69c9c4f. Setup retained a curl 7 before eventual reachability; fresh strict controls, denials and rollback passed. Both fixture cleanups and zero-owned-resource inventory were confirmed. Cluster cleanup `.runs/bootstrap/bb046173aa394dbcbe9d86ed3e889064/cleanup.json` confirmed container 3aef1990bdf0184a197a8a4d6947e107dee4219ad22c00499cf1b89d1ccccf3c absent. Review then corrected handling of a native empty EndpointSlice with null ports/endpoints and extended its guard. This run remains a pre-review pass.

Final-source run `.runs/readiness-network-002/` then passed 3 tests in 156.05s on node e0eefa2a-4105-4461-b45d-698a7719cfc1 (151 native commands). Its two setup observations took 0.326s and 0.827s; the latter retained curl 7 before both successful observations. Fresh strict controls, denials and rollback passed; fixture UIDs 2fb79ea8-d9af-4fc0-b7a5-b9ab1fa96de8 and f1ec80e3-3f73-45fc-bdd9-1dda0ec6dfe3 were checked and disappearance confirmed. Final inventory was empty of owned fixtures/PVC/PV. Cluster cleanup `.runs/bootstrap/6d8d2ded1d1546ae8e4530b7de1a652d/cleanup.json` confirmed container f4ac797e1c730c1fc1f02813c70adc9bd90027b7a6a98c4872c00de9e71fbc74 absent.

Second final-source run `.runs/readiness-network-003/` passed 3 tests in 157.96s on node 99cfdb34-c33c-47ec-9320-2d3264d76ffa (151 native commands). Its setup observations took 0.537s and 0.896s; the latter retained curl 7 before reachability. Fresh strict controls, denials and rollback passed. Fixture UIDs 0a61591b-bf24-4664-891e-e28cea47ec90 and a1b62324-f95f-4b3a-8229-bb27f31aaee1 were compared and disappearance confirmed. Final inventory had no owned fixtures/PVC/PV. Cluster cleanup `.runs/bootstrap/60db2367caeb4b1895c265fe7f25905d/cleanup.json` confirmed container 60a6f1000b838b9866029424df25c506d84ccf691f996b7911b1b72f7838d7ca absent. Original owner/kubeconfig are absent; unrelated Docker containers remain outside scope.

Final-source runs 002/003 are counted; 001 is preserved separately. The native audit reconciles JUnit (zero failures/errors/skips), exact request results, setup/denial markers, all fixture UIDs/cleanup and frozen source hashes. Each scenario retained twelve fresh denied markers and three trials per route/method, with covered positive controls and policy rollback. Across the four final-source fixtures, setup took 0.326–0.896 seconds; two setup refusals were retained. Thirty offline guards pass, all six qualification tests collect without live dispatch, compilation and whitespace pass. Native command latency is retained; exact internal controller/proxy event timing and queue metrics are unknown. No further OpenShell installation/admission/gateway/lifecycle/policy live work was dispatched in this investigation.

[PLAN-0006](../development/plans/PLAN-0006-service-readiness.md) accounts for the correction and review. ISSUE-0003 is resolved for the evidenced premature fixture-control admission: tests now begin only after observed usable Service routing, then demand fresh strict controls. All historical failed requests remain preserved; the individually unattributed historical timeout remains a limit of diagnosis. Native diagnosis and all qualification evidence remain local and ignored. Scope is the selected single-node Linux amd64 kind 0.33.0/Kubernetes 1.35.8/Calico 3.33.0 tuple with unchanged fixture/policy artifacts.

Retained failed dispatch: an offline uv invocation without the Makefile's repository cache selected a different cache and lacked SDK metadata; it failed before Python/live dispatch. Using the existing repository cache dispatched the diagnosis without changing dependencies. Read-only inspection corrections are retained in `.runs/readiness-resume/history.json`. Raw runs, state, kubeconfig, private logs and credentials are excluded from publication.

## Primary sources and remaining limits

- [Kubernetes v1.35 EndpointSlice conditions and ownership](https://v1-35.docs.kubernetes.io/docs/concepts/services-networking/endpoint-slices/).
- [Kubernetes Service proxy behavior](https://kubernetes.io/docs/reference/networking/virtual-ips/) and [v1.35 proxy synchronization parameters](https://v1-35.docs.kubernetes.io/docs/reference/command-line-tools-reference/kube-proxy/).
- [Selected kind release](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0) and [Calico release](https://github.com/projectcalico/calico/releases/tag/v3.33.0), still current at this investigation; runtime-lock inputs remain unchanged.

The bounded correction establishes an observed prerequisite before qualification begins. It does not promise instantaneous Service readiness after Pod Ready, diagnose every historical timeout, measure fleet reliability or qualify multi-node behavior. Further OpenShell policy, toolchain/recovery, adapters, agents and Temporal work requires its separate admission/qualification.
