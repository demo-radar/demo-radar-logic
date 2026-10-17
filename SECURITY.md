# Reporting a security concern

For a sensitive report, use the contact published in **Impressum** on
[Demo Radar](https://demo-radar.com). Open the demonstration list and select
Impressum to find the current operator contact. Include “DemoLogic security” in
the subject so the affected service is clear.

Describe the affected revision, observed behavior and a minimal synthetic
reproduction. Do not post credentials, session cookies, private event exports,
review records or journal contents in a public issue. Share sensitive evidence
privately after agreeing a suitable channel. There is no guaranteed response time
or bug-bounty program stated here.

Ordinary bugs and documentation suggestions can use repository issues when
available. The [contribution guide](CONTRIBUTING.md) explains local checks.

## Dependency checks

Run `uv audit --locked` before releasing. It checks the locked dependencies,
including optional notebook/model groups. CI fails on reported vulnerabilities;
there are no advisory suppressions. Use
`uv audit --locked --python-platform aarch64-unknown-linux-gnu` to check the
service runner's platform explicitly.

Keep Transformers and Hugging Face Hub version limits compatible when updating
the research group. Run the synthetic semantic compatibility check described
in [notebook setup](docs/notebook-setup.md) as well as the service tests. Optional
research libraries are not installed in the production API image, but still
need security updates for people using the notebooks.
