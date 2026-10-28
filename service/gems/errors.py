"""Safe explanations for Gem input and reply failures."""

GEM_ERRORS = {
    "gem_model_mismatch": "The provider returned a model outside the approved Gem configuration. No suggestion was accepted; its attempt and usage remain saved.",
    "gem_input_too_large": "The full Gem context exceeds the input limit. No fields were dropped and no model call was admitted.",
    "invalid_gem_response": "The model returned invalid Gem JSON. No suggestion was accepted; the attempt and usage were saved.",
}
