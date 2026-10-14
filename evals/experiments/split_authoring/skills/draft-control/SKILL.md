---
name: draft-control
description: Draft the benign control through the real application seam.
---

Your objective is one benign control probe. Call the real production implementation with the planned
ordinary input and establish meaningful ordinary behavior and required fixture preconditions.
The unchanged control must remain valid when the reported security defect is fixed. Assert stable
application behavior or dependency interactions needed to establish that the intended operation ran.
Do not assert the current implementation's incidental representation, algorithm, formatting, ordering
or unsafe behavior. Do not require the security fix; adversarial safety belongs to the exploit probe.
If a planned observation could change during a legitimate fix, choose another stable observation at
an existing seam, or state why none is available. A fixed response from a dependency double alone
is insufficient: establish the relevant production call and ordinary interaction too. The double may
record and supply data, but must not reproduce production logic or implement the security property.
Write only the control's approved file. Preserve the exact planned native identity. Before finalizing,
check that your assertion proves the benign operation and tolerates implementation changes that
preserve ordinary behavior. Return blocked if source or seams cannot support this claim.
