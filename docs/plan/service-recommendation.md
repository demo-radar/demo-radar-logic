# Service recommendation

The delivered workflow prepares suggestions for staff review. It uses Qwen on
Hetzner with rubric v4, preserves saved outcomes and supports explicitly approved
recurring-event reuse in Demo Radar. Gemini remains a research comparison; its
production adapter is not implemented.

The [fresh-case comparison](../results/fresh-v4-confirmation.md) found good
precision and coverage but recall below the project target for both candidates.
The [practical trial](../results/practical-trial.md) did not establish reliable
time savings. Neither result supports describing model suggestions as automatic
ground truth. Reviewer approval and the recorded reference limitations remain central.

## Measure the application benefit

| Measure | Counting rule |
| --- | --- |
| New-model quality | First suggestions against independently prepared references; include failures and abstentions |
| Approved reuse | Events completed through an explicit reusable approval; keep separate from model calls |
| Staff effort | Active minutes including research, corrections and group review per comparable workload |
| Backlog | Pending/unresolved events and their age; suggestions alone are not completed public tags |
| Corrections | Edited/rejected suggestions, rule reversals and problems found in reused assignments |

Record recurrence frequency and topic mix when comparing periods. Group approval
can reduce actions without improving the model. Reusing an incorrect decision can
also multiply its harm, so inspect reuse quality and allow the rule to be disabled.

The [architecture decision](../adr/0001-capstone-backoffice-ml-vs-llm.md) describes
ownership. The [API guide](../service-api.md) describes limits and recovery.
Original study evidence is in [research replay](../research-replay.md).
