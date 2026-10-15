# Public package boundary

This repository publishes source, tests, versioned model instructions, research
methods, selected aggregate results and reviewed examples. Private event exports,
reviewer reference labels, per-event predictions, model artifacts, provider responses,
runtime credentials and recovery journals are not included.

The code is licensed under [Apache License 2.0](../LICENSE). That code license is
not a grant to redistribute private data or third-party model weights. Keep source
and model attribution with their materials, and check the selected screenshots,
quotations and presentation exports before sharing them.

Public examples use invented events or explicitly selected public-title screenshots.
An example is not an endorsement of its slogan or a verified account of an event.
Topic labels do not assess a participant, organizer, political desirability or truth.

Historical research reviews retain their dates and limitations. Internal schedules,
personal approvals and release/recovery logs are maintained in the issue tracker.
The [replay guide](research-replay.md) identifies original input bytes; public
redaction does not silently change an old run’s recorded provenance.

The public release starts from a reviewed source snapshot without the earlier
private Git history. Original commits, retired decks/PDFs and internal work logs
remain in the private research archive or issue tracker. Historical replay
requires authorized access to that archive and the matching private inputs.

A selected presentation export needs its own review of notes, hidden slides,
metadata and embedded files before sharing.

The [publication checker](../scripts/check_public_repo.py) checks the Git index
for common private paths and saved notebook outputs. It does not inspect arbitrary
secret formats, images, remote artifacts or every historical object. See the
[synthetic guide](reproducibility.md) for software checks and
[security reporting](../SECURITY.md) for sensitive concerns.
