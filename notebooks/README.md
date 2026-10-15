# Notebook index

Notebooks record the research progression; they are not a public dataset or an
instruction to run new provider calls. For the software demonstration, use the
[synthetic workflow](../docs/reproducibility.md). For historical experiments,
start with [research replay](../docs/research-replay.md) and the matching private
inputs. Old source fingerprints must not be replaced with the latest rubric.

All experiments below need authorized private inputs to reproduce their scores.
Saved-result replay needs the matching private cache/reports. Live model runs
add provider credentials and separate approval. Notebook outputs are cleared in Git.

| Notebook | Question | Additional requirement |
| --- | --- | --- |
| [01 · Snapshot quality](01_data_snapshot_and_quality.ipynb) | What was exported and excluded? | Prepared snapshot and manifest |
| [02 · Labels, grouping and splits](02_label_audit_eda_and_splits.ipynb) | Can related events leak across splits? | Frozen benchmark/review bundle |
| [03 · Simple baselines](03_simple_baselines.ipynb) | What can cheap rules achieve? | Benchmark and reviewed pilot |
| [04 · Classical text models](04_classical_text_models.ipynb) | Do word/character TF-IDF classifiers improve tagging? | Locked notebook dependencies and baseline reports |
| [05 · Context features](05_context_and_nearby_places.ipynb) | Do existing time/location fields help? | Matching trained-model reports |
| [06 · Semantic models](06_semantic_models.ipynb) | Does NLI improve tagging, and how is its score formed? | Semantic dependency group; first run downloads model weights |
| [07 · Hosted LLM comparison](07_llm_comparisons.ipynb) | How do prompt variants compare? | Saved cache, or approved Groq/Hetzner calls |
| [07a · Reference review](07a_development_reference_review.ipynb) | What changes when the answer key changes? | Saved predictions and reviewed references; no new inference |
| [07b · Hetzner candidates](07b_hetzner_model_comparison.ipynb) | How do two fixed hosted candidates compare? | Cache, or approved Hetzner calls |
| [08 · Search comparison](08_research_evidence_comparison.ipynb) | Does verified live search help the same model? | Cache, or approved Groq calls |
| [08a · Supplied search results](08a_qwen_search_results.ipynb) | Does fixed external evidence help Qwen? | Frozen research packets; cache or approved calls |
| [09 · Selection policy](09_thresholds_and_hybrid_policy.ipynb) | Which development candidates should enter the final comparison? | Matching saved candidate reports |
| [10 · Original final benchmark](10_final_benchmark_and_recommendation.ipynb) | How do three fixed candidates score on final references? | Final bundle, fitted artifacts and saved predictions |
| [11 · API cost audit](11_api_cost_audit.ipynb) | What was sent, measured or left unknown? | Private attempt logs/ledgers; no new inference |
| [12 · Gemini search](12_gemini_search_comparison.ipynb) | Did the search switch actually invoke retrieval? | Cache, or approved Gemini calls |
| [13 · Required evidence](13_gemini_required_evidence.ipynb) | Does verified evidence help three Gemini candidates? | Research packets and cache, or approved calls |
| [14 · Broader comparison](14_gemini_broader_comparison.ipynb) | Do development findings carry across more cases? | Saved reports/cache or approved calls |
| [15 · Gem adaptation](15_demo_radar_gem_search.ipynb) | Do the application’s Gem instructions and search help? | Fixed prompts/reference groups and cache or approved calls |
| [16 · Reconciled reference](16_reconciled_reference_comparison.ipynb) | Can candidates be compared against one answer key? | Versioned references and unchanged saved predictions |
| [17 · Tag limit](17_tag_limit_comparison.ipynb) | Does a third tied tag help? | Fixed references and paired saved runs |
| [18 · Practical review](18_practical_tagging_trial.ipynb) | Do suggestions reduce active review effort? | Private trial packet, saved model answers and reviews |
| [19 · Confidence diagnostic](19_confidence_and_targeted_search.ipynb) | Do uncertainty warnings identify errors? | Private reviewed cases/cache; live work is separately gated |
| [20 · Background knowledge](20_background_knowledge_comparison.ipynb) | What changes with the full rubric and learned knowledge? | Fixed reviewed cases and saved paired requests |
| [21 · Rubric delivery](21_reviewed_rubric_delivery.ipynb) | Does removing process history help with the same rules? | Reviewed cases and saved paired requests |
| [22 · Rubric v4](22_rubric_v4_comparison.ipynb) | Does the revised policy package improve familiar-case agreement? | 54 reviewed cases, paired configurations and saved answers |
| [23 · Fresh confirmation](23_fresh_v4_confirmation.ipynb) | Does fixed v4 work on fresh cases? | Frozen fresh reference, selection and saved answers |

Use the [results index](../docs/results/README.md) for safe aggregate conclusions.
The [setup guide](../docs/notebook-setup.md) explains the notebook/semantic groups;
the external Jupyter Docker setup is optional local tooling. Keep every live-run
flag off when inspecting saved work. Missing private inputs should stop a replay,
not trigger new model requests or invented replacement labels.
