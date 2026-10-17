# Running the notebooks

The project uses Python 3.13; `uv.lock` records its dependency versions. For a clean public checkout, start with the [synthetic reproduction guide](reproducibility.md). You can launch Jupyter directly with `uv run --locked --group notebooks jupyter lab`; the private experiment notebooks still require the inputs listed below.

The Docker instructions below describe an optional local Jupyter setup. Its Compose file is outside this repository, so it is not required or supplied by the public workflow.

## 1. Start Jupyter with Docker Compose

Use `docker-compose-demo-logic.yml` from your Jupyter Docker setup. This Compose file and its Dockerfile are maintained outside this repository. It must define the `jupyter-demo-logic` container, include uv in the image, and mount your DemoLogic checkout at `/home/jovyan/work`.

From the directory containing that Compose file, run the following on your host. Replace the example checkout path with your own:

```bash
export DEMO_DIR=/absolute/path/to/demo-radar-logic
docker compose -f docker-compose-demo-logic.yml up -d --build jupyter-demo-logic
```

The existing Compose setup uses `DEMO_DIR` for the repository mount and exposes Jupyter at `http://localhost:9000`. Keep `DEMO_DIR` set when running other Compose commands for this file. TensorBoard is not required for these data-audit notebooks.

## 2. Enter the container and install dependencies

From your host terminal, open a shell inside the running container:

```bash
docker exec -it -w /home/jovyan/work jupyter-demo-logic bash
```

Then run these commands **inside that shell**:

```bash
cd /home/jovyan/work
export UV_PROJECT_ENVIRONMENT=/home/jovyan/.venvs/demo-logic
uv sync --locked --group notebooks
uv run --locked --group notebooks python -m ipykernel install --user --name demo-logic --display-name "DemoLogic (uv)"
```

`uv sync` installs the locked project dependencies and obtains Python 3.13 if needed. The environment path keeps Linux packages inside the container instead of reusing a possible macOS `.venv` in the mounted checkout. Kernel registration makes this environment available to the Jupyter server that Compose already started.

Set `UV_PROJECT_ENVIRONMENT` again when opening a new container shell to run project commands. Repeat dependency installation and kernel registration after recreating the container unless those directories are persisted.

## 3. Open and run a notebook

Open `http://localhost:9000`, refresh the kernel list if necessary, and select **DemoLogic (uv)**. Use **Restart Kernel and Run All Cells** to check the complete workflow. Avoid installing packages from notebook cells: add needed dependencies to the notebook dependency group and update the lockfile instead.

## Optional semantic-model environment (Notebook 06)

Inside the same container shell, install the extra dependencies before opening Notebook 06:

```bash
cd /home/jovyan/work
export UV_PROJECT_ENVIRONMENT=/home/jovyan/.venvs/demo-logic
uv sync --locked --group semantic
```

Restart **DemoLogic (uv)** after installation. The semantic group includes the ordinary notebook dependencies plus CPU PyTorch, Transformers, and SentencePiece. Use this group whenever you sync an environment that must run Notebook 06; syncing only the smaller `notebooks` group can remove the semantic packages.

The first model run downloads about 562 MB into the ignored `artifacts/hf-cache/` folder. This is in the mounted repository and survives container recreation. The Python environment still needs installation after recreation, as described above. Allow several GB of available memory for the float32 CPU run; the notebook reports measured process memory and speed. Public CI uses synthetic tests and does not download model weights or access the private benchmark.

### If tqdm warns that IProgress is missing

This warning concerns the notebook progress bar, not the model predictions. The locked `notebooks` group includes `ipywidgets`, and `semantic` includes that group. From `/home/jovyan/work` in the container, set `UV_PROJECT_ENVIRONMENT=/home/jovyan/.venvs/demo-logic` and run `uv sync --locked --group semantic`. Then restart the **DemoLogic (uv)** kernel and rerun the notebook.

If progress bars still render only as text, refresh JupyterLab. When the Jupyter server and kernel use different Python environments, the server also needs `jupyterlab_widgets`; installing `ipywidgets` in the kernel alone does not provide that server extension. See the [official widget installation guide](https://ipywidgets.readthedocs.io/en/stable/user_install.html). Keep the server extension in the Compose image's dependencies if it needs adding.

### Model-library deprecation warnings

Notebook 06 uses `dtype=torch.float32` when loading the model. Older copies used the deprecated `torch_dtype` argument; reload the saved notebook to pick up the change.

The supported research environment now requires Transformers 5.10.1 or newer
and Hugging Face Hub 1.5 or newer. The lockfile chooses the exact compatible
versions. These are optional research dependencies; the production service
image installs only its `service` group.

After updating a notebook environment, restart its kernel. Run
`uv run --locked --group semantic python scripts/check_semantic_environment.py`
to check DeBERTa inference and safe local weight reload using synthetic data.
This downloads packages, not model weights, and sends no LLM requests. CI runs
the same offline check. The upstream DeBERTa implementation can still emit a
`torch.jit.script` deprecation warning; it does not fail that check.

Saved research scores keep the library versions recorded when they were run.
A synthetic compatibility check does not prove identical predictions from a
real checkpoint. Use the original research revision from the
[replay guide](reproducibility.md) to reproduce old experiments. Do not replace
historical scores or mix new library timings into the old comparison.

### CPU and GPU on a MacBook

The current Jupyter Linux container uses the CPU. Docker Desktop does not pass the Mac's Metal GPU through to this container. A separate native macOS Python environment can use PyTorch's MPS backend on supported hardware; that would require moving both the model and input tensors to MPS and measuring compatibility, predictions, and speed separately. Notebook 06 currently pins CPU inference. Do not mix timings or cached scores from different devices.

Docker Model Runner can use host-side Metal for supported models, but that does not enable GPU access inside this Jupyter container or establish support for our NLI checkpoint. See [Docker's explanation](https://www.docker.com/blog/docker-model-runner-vllm-metal-macos/) and [PyTorch MPS documentation](https://docs.pytorch.org/docs/main/notes/mps.html).

### Shared notebook tools and tests

Repeated table display and fingerprint checks live in `notebooks/tools/`, using the repository's existing plural folder name. For example, a notebook calls `show_table(columns, records)` or `verify_sha256(path, expected_hash)` once. Model definitions, tag descriptions, fitting, cutoff selection, and experiments stay in the notebooks. Shared data validation and evaluation remain in `src/demo_logic/`.

Keep `tests/test_semantic_notebook.py`: it tests scoring arithmetic, tie handling, invalid outputs, and exclusion of final-test records using synthetic data. It does not download or run the model. These checks protect the experiment from coding mistakes; measured tagging quality still comes from the notebook. Tests for display, fingerprints, and review export live in `tests/test_notebook_tools.py`.

Notebooks 04 and 06 also share saved-report matching, prediction alignment by event ID, and comparison-row formatting. `notebooks/tools/reports.py` rejects incompatible report inputs and duplicate, missing, or unexpected prediction IDs. The notebook still chooses which candidates and metrics to compare. Synthetic regression checks are in `tests/test_notebook_reports.py`.

## Hosted LLM settings (Notebook 07)

Keep keys and run controls in the repository-root `.env`. On a fresh checkout, copy `.env.example` to `.env` and fill in your Groq and Hetzner keys. Keep an existing configured `.env`; never commit or display its contents.

The current Docker setup mounts the whole repository at `/home/jovyan/work`, so Notebook 07 can read `/home/jovyan/work/.env` directly. No extra Compose `env_file` entry is needed. A file elsewhere on your Mac is not automatically visible in the container.

Default settings replay existing results without API calls. To resume the experiment, edit these two lines in `.env`:

```dotenv
NOTEBOOK07_RUN_LIVE=true
NOTEBOOK07_STAGE=screen
```

Run All, then switch the stage to `check` once screening is complete. Set live mode back to `false` to review cached results. The notebook rereads the file on setup and displays the active settings without credentials. Existing process environment variables take precedence; changing those requires updating the environment and restarting the kernel.

`NOTEBOOK07_MAX_RETRY_WAIT_SECONDS=120` allows ordinary free-tier resets with progress messages. Longer waits pause the provider; successful answers stay cached. The `python-dotenv` dependency is locked in the notebook group. After pulling, sync inside the container as described above; use `--group semantic` if you also need Notebook 06.

## Required private inputs

Notebook 01 needs `data/dataset.jsonl` and its matching `data/manifest.json`. It checks the snapshot and writes an aggregate quality report under the Git-ignored `reports/` directory.

Notebook 02 also needs the five-file [private benchmark bundle](data-preparation.md#restore-the-private-benchmark). It reads the saved assignments and review files, checks that they agree, and displays the audit. It does not redraw the split, apply group-review decisions, or overwrite your labels. A successful run confirms file consistency, not that review is complete or every label is correct.

Notebook 03 defines the baseline rules and runs each comparison in visible cells. The keyword dictionary and title normalization are copied from Demo Radar, with source revision and fingerprints recorded in the notebook. A synthetic example explains matching. The benchmark applies its own tag-selection policies, so these results describe the regex component, not the complete production autofill workflow. Shared `evaluation.py` keeps metric calculations consistent across later notebooks; snapshot and benchmark loaders check input integrity. Modeling and evaluation come first; the optional service is built after selecting an approach.

Notebook 03 needs the same bundle with locked split membership, taxonomy v2 and completed pilot labels. It compares common-tag, keyword and historical-tag rules on development records. Repeat-event simulation results are shown separately. Each run writes one private timestamped JSON report under `reports/baselines/`, including input/code fingerprints, metrics and predictions. It does not edit the benchmark or score final-test labels. Read the limitations before interpreting the pilot results as evidence for a model choice.

Notebook 04 adds the locked `scikit-learn` dependency to the notebook group, so rerun `uv sync --locked --group notebooks` in the container after pulling this change. It fits word and word-plus-character TF-IDF classifiers, compares them with a matching Notebook 03 report, and saves a private report under `reports/classical/` plus a fitted artifact under `artifacts/classical/`. It uses training and validation labels only. The 40 reviewed pilot labels are development diagnostics; the 149 final-test labels stay untouched. Follow the [Week 2 review checklist](methodology.md#comparison-stages).

Notebook 06 uses the same benchmark and compatible private reports from Notebooks 03 and 04. It scores the 188 development representatives with the pinned NLI model and saves `reports/semantic/<run-id>.json`. Per-event scores under `reports/semantic-cache/` let a rerun resume completed inference. The notebook checks cache identities and distinguishes reused scores from newly measured inference time. It does not fit on historical training tags or score final-test labels. Follow the [DR-18 review steps](methodology.md#comparison-stages).

It also writes `reports/semantic-review/<run-id>.md` with all historical-label disagreements in the separate check subset (85 of 94 examples in the 28 September run). Review the title, both tag lists, and relevant scores; then fill in **Decision**, **Preferred tags**, and **Reason / source**. A disagreement alone does not identify which side is wrong. Keep this file private. Reruns create a new file and never overwrite your notes. Accepted corrections should produce a versioned development-label update and comparisons rerun consistently across candidates; they must not silently replace the historical benchmark or become independent final-test labels.

If an input is missing or inconsistent, stop and restore or reconcile the matching files. Do not create empty review forms to make the notebook run. Repository access alone does not provide access to these private inputs.

## Before committing

Clear notebook outputs and execution counts before saving. Keep private data, review CSVs, and reports outside Git. In the container shell from step 2, run:

```bash
uv run --locked --group notebooks --group service pytest
uv run --locked python scripts/check_public_repo.py
```
