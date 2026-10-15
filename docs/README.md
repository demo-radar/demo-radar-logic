# Documentation

Start with the route that matches your question.

| Question | Read |
| --- | --- |
| What can I run without data or API keys? | [Public synthetic workflow](reproducibility.md) |
| How are the application and AI service connected? | [Current architecture](architecture.md) and [historical decisions](adr/0001-capstone-backoffice-ml-vs-llm.md) |
| What does the service accept and return? | [API and recovery](service-api.md) |
| How were the models evaluated? | [Methodology and limits](methodology.md) |
| Which experiment should I open? | [Notebook index](../notebooks/README.md) |
| Where are the aggregate findings? | [Results index](results/README.md) |
| Who reviews labels and suggestions? | [Reviewer terminology](methodology.md#review-terminology) |
| What are the topic definitions? | [Current v4 input](rubrics/tagging-rubric-v4.md) and [policy change record](rubrics/v4-review.md) |
| What did the project teach us? | [Research lessons](presentation/insights.md) |
| How are daily briefings produced? | [Daily-summary design](plan/daily-summary.md) |
| How do authorized researchers prepare private inputs? | [Data preparation](data-preparation.md) and [notebook setup](notebook-setup.md) |
| How do I replay the historical experiments exactly? | [Research replay](research-replay.md) |

The public service walkthrough uses invented fixtures. Historical notebooks need
authorized private inputs; they are not a complete public dataset. Versioned
model inputs and saved references identify a particular experiment, not a
promise about a hosted model’s future behavior.

Current architecture and service guides describe implemented behavior. Dated
research reports describe their original studies. Later delivery does not turn
an earlier score into a production-quality claim. Internal schedules, approval
conversations and release checklists are maintained in the project’s issue tracker.
