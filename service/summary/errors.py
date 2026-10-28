"""Safe explanations for daily summary failures."""

SUMMARY_ERRORS = {
    "summary_disabled": "Daily draft generation is disabled by the operator.",
    "summary_input_too_large": "The complete daily snapshot exceeds the input limit. No events were dropped.",
    "invalid_summary_envelope": "The provider response is missing the completion fields. The attempt was saved as failed.",
    "incomplete_summary_response": "The provider did not finish the summary. No partial draft was accepted.",
    "summary_model_mismatch": "The provider returned a model outside the pinned summary configuration.",
    "invalid_summary_json": "The summary was not valid JSON. The attempt was saved as failed.",
    "summary_word_limit": "The completed summary exceeded its writing word budget. The attempt and usage were saved as failed.",
    "summary_example_leakage": "The summary copied an example phrase without support in its cited sources. The attempt and usage were saved as failed.",
    "invalid_summary_schema": "The summary did not match the required fields or length limits. The attempt was saved as failed.",
    "invalid_summary_citations": "The draft cites missing or duplicate event IDs. Staff review is required.",
}
