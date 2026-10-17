"""Check the notebook model API with synthetic weights and no downloads."""

import tempfile

import torch
from transformers import AutoModelForSequenceClassification, DebertaV2Config


def check():
    model = AutoModelForSequenceClassification.from_config(
        DebertaV2Config(
            vocab_size=32,
            hidden_size=24,
            num_hidden_layers=1,
            num_attention_heads=2,
            intermediate_size=48,
            num_labels=3,
        )
    )
    inputs = {
        "input_ids": torch.tensor([[1, 2, 3]]),
        "attention_mask": torch.ones(1, 3, dtype=torch.long),
    }
    model.eval()
    with torch.inference_mode():
        expected = model(**inputs).logits
    with tempfile.TemporaryDirectory() as folder:
        model.save_pretrained(folder, safe_serialization=True)
        restored = AutoModelForSequenceClassification.from_pretrained(
            folder, local_files_only=True, trust_remote_code=False
        )
        restored.eval()
        with torch.inference_mode():
            actual = restored(**inputs).logits
    assert tuple(actual.shape) == (1, 3) and torch.isfinite(actual).all()
    torch.testing.assert_close(actual, expected)
    print("Synthetic DeBERTa inference and safe local reload passed. No model downloads.")


if __name__ == "__main__":
    check()
