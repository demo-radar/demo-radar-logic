"""Private Jupyter review controls shared by practical tagging trials.

Sampling, model calls and analysis belong in the notebook. This module manages
only timing, safe rendering and saving a human response without overwriting it.
"""

import math
import time
from html import escape

from demo_logic.notebook_support import save_private_json
from notebooks.tools.hashes import fingerprint


class ReviewClock:
    """Measure active time and its context-lookup subset using a monotonic clock.

    Paused time is excluded. Context lookup is included in total active time,
    so it must never be added to that total again during analysis.
    """

    def __init__(self, clock=time.perf_counter):
        self.clock = clock
        self.last = None
        self.active = 0.0
        self.context = 0.0
        self.lookup = False
        self.started = False

    def _accrue(self):
        if self.last is not None:
            now = self.clock()
            elapsed = now - self.last
            self.active += elapsed
            if self.lookup:
                self.context += elapsed
            self.last = now

    def resume(self):
        """Start/resume without counting a pause or resetting previous time."""
        if self.last is None:
            self.started = True
            self.last = self.clock()

    def pause(self):
        """Stop active timing, preserving the current context-lookup mode."""
        self._accrue()
        self.last = None

    def set_lookup(self, enabled):
        """Switch timing categories at the instant the reviewer toggles lookup."""
        self._accrue()
        self.lookup = bool(enabled)

    def values(self):
        """Return elapsed seconds without stopping an active session."""
        self._accrue()
        return self.active, self.context


def validate_review(answer, allowed):
    """Reject incomplete answers before saving; preserve all human-selected tags.

    An unclear case may have no final tags. A resolved empty set is allowed when
    no catalog tag fits. Scores must exclude unclear answers and report them.
    """
    tags = answer["final_tags"]
    if not isinstance(tags, list) or len(set(tags)) != len(tags) or set(tags) - set(allowed):
        raise ValueError("Choose distinct tags from the approved catalog.")
    if answer["status"] not in {"resolved", "unclear"}:
        raise ValueError("Choose resolved or unclear.")
    if answer["prior_exposure"] not in {"no", "yes", "unsure"}:
        raise ValueError("Record whether you have seen this event before.")
    if type(answer["context_needed"]) is not bool:
        raise ValueError("Record whether context was needed.")
    active, context = answer["active_seconds"], answer["context_seconds"]
    if (
        any(type(v) not in (int, float) or not math.isfinite(v) for v in (active, context))
        or active <= 0
        or context < 0
        or context > active
    ):
        raise ValueError("Timing must be positive, with lookup time inside active time.")
    if (answer["status"] == "unclear" or not tags) and not answer["notes"].strip():
        raise ValueError("Add a short reason for an unclear or empty answer.")


def show_trial_review(events, predictions, folder, tags, contract_sha256):
    """Display one timed event at a time and save a private JSON answer per event.

    Completed answers are preserved on rerun. Start reveals the title and the
    assigned model's suggestion together. Pause excludes interruptions; lookup
    mode measures the part of active work spent finding context. No network or
    model call happens here. A kernel restart loses only the unsaved timer.
    """
    import ipywidgets as w
    from IPython.display import display

    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    panel = w.VBox()

    def render():
        remaining = [e for e in events if not (folder / (e["external_id"] + ".json")).exists()]
        if not remaining:
            panel.children = (w.HTML("<b>All 20 reviews saved. Run the analysis cell below.</b>"),)
            return
        e = remaining[0]
        timer = ReviewClock()
        info = w.HTML(
            f"<b>Review {len(events) - len(remaining) + 1}/{len(events)} — {escape(e['workflow'])}</b>"
        )
        body = w.HTML("Press Start when ready. The title is hidden until timing begins.")
        start, pause, save = (
            w.Button(description="Start / resume"),
            w.Button(description="Pause"),
            w.Button(description="Save and next", button_style="success"),
        )
        lookup = w.ToggleButton(description="Looking up context", disabled=True)
        selected = w.SelectMultiple(
            options=tags,
            description="Final tags",
            rows=len(tags),
            disabled=True,
            layout=w.Layout(width="500px"),
        )
        status = w.Dropdown(
            options=[("Choose status", None), ("Resolved", "resolved"), ("Unclear", "unclear")],
            description="Decision",
        )
        seen = w.Dropdown(
            options=[("Choose", None), ("No", "no"), ("Yes", "yes"), ("Unsure", "unsure")],
            description="Seen before?",
        )
        need = w.Dropdown(
            options=[("Choose", None), ("No", False), ("Yes", True)], description="Need context?"
        )
        notes, sources = w.Textarea(description="Notes"), w.Textarea(description="Sources")
        message = w.HTML("")
        suggestion = predictions.get(e["external_id"])

        def begin(_):
            timer.resume()
            selected.disabled = False
            lookup.disabled = False
            offered = ", ".join(suggestion["predicted"]) if suggestion else "Choose tags yourself."
            if suggestion and not suggestion["predicted"]:
                offered = "No suggestion — choose tags yourself or mark unclear."
            body.value = (
                "<p>" + escape(e["title"]) + "</p><p><b>Suggestion:</b> " + escape(offered) + "</p>"
            )
            message.value = "Timer running. Hold Cmd/Ctrl to select multiple tags."

        def stop(_):
            timer.pause()
            message.value = "Paused. Press Start / resume before continuing."

        def store(_):
            if not timer.started:
                message.value = "Press Start and review the event first."
                return
            timer.pause()
            active, context = timer.values()
            answer = {
                "external_id": e["external_id"],
                "workflow": e["workflow"],
                "contract_sha256": contract_sha256,
                "title_sha256": fingerprint(e["title"]),
                "prediction_sha256": fingerprint(suggestion) if suggestion else None,
                "final_tags": list(selected.value),
                "status": status.value,
                "prior_exposure": seen.value,
                "context_needed": need.value,
                "active_seconds": active,
                "context_seconds": context,
                "notes": notes.value,
                "source_links": sources.value,
            }
            try:
                validate_review(answer, tags)
                save_private_json(folder / (e["external_id"] + ".json"), answer)
            except (ValueError, FileExistsError) as error:
                message.value = escape(str(error)) + " Timing paused; resume before continuing."
                return
            render()

        start.on_click(begin)
        pause.on_click(stop)
        save.on_click(store)
        lookup.observe(lambda change: timer.set_lookup(change["new"]), names="value")
        panel.children = (
            info,
            w.HBox([start, pause, lookup]),
            body,
            selected,
            status,
            seen,
            need,
            notes,
            sources,
            save,
            message,
        )

    render()
    display(panel)
    return panel
