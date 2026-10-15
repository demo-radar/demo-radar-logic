# Fresh-case confirmation: method

**Historical study, 7 October 2026.** This checked fixed rubric-v4 Qwen and Gemini
configurations on cases outside the 54 familiar development examples. It was a
confirmation of those configurations, not another v3/v4 tuning comparison.
Read the [aggregate results](../results/fresh-v4-confirmation.md) and
[original replay instructions](../research-replay.md).

## Source and selection

The captured public Berlin feed contained 1,363 listed occurrences. The candidate
date window was 7 October–6 November 2026; listings do not confirm actual attendance
or that a planned gathering occurred. The pool had 191 normalized titles. Overlap
screening excluded 95; close-title review merged one more; campaign/meaning review
withheld 14; two further named-event families were merged. These screens reduce
known overlap, not prove independent event identities.

Forty selected event types were reviewed before model predictions. The private
reference version retained 38 resolved and two unclear decisions. Four resolved
cases had familiarity/possible-overlap flags, leaving **34 primary fresh cases**.
Nine resolved cases required additional context; 29 were marked title-sufficient.
References could contain more than the model’s two allowed suggestions.

## Fixed comparison

Each model received the original German title and full v4 rubric, with learned
background knowledge allowed and search off. No translated title, separate
location/date fields, private notes or reference tags entered the request.
Settings and references stayed fixed once inference began.

Primary correctness scores use the 34 fresh resolved cases. All 38 resolved
cases and the context-needed/title-sufficient subsets are also reported.
Unclear cases retain status and raw coverage without becoming correctness labels.
Report per-tag support, exact match, failures, original duration, usage estimates
and the recall ceiling imposed by the two-tag cap.

## Limits and interpretation

One annotator supplied the reference. Some labels rely on extra context or a
policy interpretation that differs from the written rule. A missing reference
tag is not by itself proof of a model mistake. The small study cannot certify
all twelve categories or establish a general winner from a small score difference.
Repeated tuning on these answers would make them development data.

The paired requests and scores were checked offline; the
[technical review](../audits/2026-10-07-fresh-v4-run-audit.md) found no calculation
error and retained the interpretation limitations. AI-assisted arithmetic checks
are not independent reference-label review. Original private labels, scores and run
ledgers remain unchanged.
