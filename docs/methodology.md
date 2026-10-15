# Research method and limitations

## Question and scope

Can topic suggestions help maintain a live demonstration map? The experiment
compared inexpensive rules, trained text classifiers, natural-language inference
and hosted language models. The task is multi-label classification of a slogan’s
main topics, with at most two model suggestions. It is not a truth check, a risk
assessment of a demonstration or a classification of individual participants.

The project set 80% micro precision, 80% micro recall and 95% suggestion coverage
as its joint quality target. These are project requirements, not universal
standards. Staff effort, original request duration, failures and estimated cost
were considered separately. A useful reviewed service is a different
objective from a model passing the automatic-tagging quality target.

## Review terminology

A **reviewer** is a person who checks reference labels or decides whether to
approve a model suggestion. This is the same role previously called a human
annotator or human reviewer. An AI-assisted technical check is identified as
such and does not count as an independent reviewer. Operators and admins have
separate operational responsibilities.

Versioned model inputs and stored provenance may retain older terms such as
`human`. Those exact values are preserved for compatibility and historical
replay; they do not describe a second role. “Human Rights” is a topic name.

## Data and reference labels

The source was a private, versioned export of public Berlin demonstration
records and existing approved topic tags. Historical tags provided training
labels; they were not assumed correct. Prepared snapshots retain source hashes,
schema/taxonomy versions and exclusion counts. The taxonomy has twelve topic tags.
Raw exports, completed reviews and per-event predictions are not public fixtures.

Repeated and strongly related titles were grouped before splitting, so dated
editions of the same event type stayed together. The original split had 732
training and 188 validation representatives. The reserved final review covered
149 dated occurrences representing 123 groups. Two confirmed development/final
duplicates were excluded before final inference, leaving 121 scored groups.
Unknown semantic overlaps may remain; title similarity is not proof of event identity.

One reviewer supplied the reviewed references. Review stages recorded
their rubric version, supported tags, uncertainty and any context used. References
were set before the relevant model predictions, but later development cases
were revisited. They must not be described as untouched independent tests.
AI-assisted reviews and arithmetic checks do not provide a second reviewer.

## Comparison stages

| Stage | What it can show | Main evidence |
| --- | --- | --- |
| Initial rules, TF-IDF, context and NLI | How fixed candidates behave on historical development labels | [Notebooks 03–06](../notebooks/README.md) |
| Original final comparison | Three pinned candidates on the same 121 reviewed groups | [Final evaluation](plan/final-evaluation.md) |
| Reconciled development references | How unchanged predictions score against a revised answer key | [Reviewed comparison](results/reviewed-comparison.md) |
| Paired rubric v3/v4 study | Effect of the whole revised policy/example package on 54 familiar cases | [Rubric comparison](results/rubric-v4-comparison.md) |
| Fresh v4 confirmation | Fixed v4 candidates on a separate 34-case primary subset | [Fresh results](results/fresh-v4-confirmation.md) |
| Practical review trial | Descriptive effort and corrections across 20 cases | [Timing trial](results/practical-trial.md) |

Development prompts and cutoffs used development records. The original final
configuration was fixed before scoring its references. Later experiments on an
already examined set are follow-ups, not a replacement final test. Score changes
across different cohorts are not paired evidence of improvement.

Search comparisons record whether retrieval actually executed. Model aliases,
provider defaults, output limits and returned model identities are retained with
the private run contracts. An enabled tool setting alone does not prove search
ran, and a model name does not pin immutable weights.

## Metrics and failure handling

- Precision measures how many suggested tags match the reference; recall measures
  how many reference tags were found. Micro F1 combines these over tag decisions.
- Coverage means at least one suggestion, not correctness. Exact tag-set match
  and per-tag support are reported alongside aggregate scores.
- Complete reviewer reference sets are retained even when they exceed the model’s
  two-tag cap. The resulting recall ceiling is reported rather than truncating truth.
- Abstentions and completed invalid answers do not disappear from the denominator.
  Unclear reviewer references are excluded from correctness scoring, with their
  coverage and status reported separately. Unattempted calls leave a run incomplete.
- Original provider latency is separate from cache replay and active reviewer work.
  Token estimates, conservative reservations and invoice charges are different
  quantities. Missing usage remains unknown rather than becoming zero cost.

The original final comparison used 2,000 seeded event-group bootstrap samples
for F1 intervals. These describe sampling variation; they do not account for
reference errors, hidden overlap or provider drift.

## What remains uncertain

Some references use background unavailable from a title. Some retained answers
and written policy boundaries differ. A missing reference tag is therefore not
automatically a model reasoning failure. Two-tag output limits also explain part
of the gap. Rare tags have little evidence; the 34-case fresh check has no LGBTQ
reference examples and only one education reference.

The timing trial used one reviewer, small different batches and possible learning
effects. Assisted final answers were entered after suggestions were visible and
are not independent quality labels. No reliable causal time-saving result or
production-wide accuracy improvement was established.

Reviewer approval remains part of the delivered workflow. Topic tags should not be
treated as verified intent, neutral ground truth or a judgment about an organizer.
Future improvement claims need new evaluation data and a declared comparison.

## Traceability and replay

Public notebooks, prompts, configurations and aggregate results describe the
experiments. Private snapshots, labels, predictions, attempt ledgers and model
artifacts retain the full evidence chain. See [research replay](research-replay.md)
for the original revision and fingerprint boundary. Public synthetic checks
verify software behavior; they cannot reconstruct withheld model scores.
