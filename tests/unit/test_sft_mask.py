"""The SFT loss mask: loss must start right after the LAST assistant marker."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "sft_train", Path(__file__).resolve().parents[2] / "training" / "sft_train.py")
sft = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sft)

T = [7, 8, 9]   # stand-in for the tokenised "<|im_start|>assistant\n"


def test_loss_starts_after_the_marker():
    assert sft.response_start([1, 2, 7, 8, 9, 4, 5], T) == 5


def test_uses_the_last_marker():
    assert sft.response_start([7, 8, 9, 1, 7, 8, 9, 2, 3], T) == 7


def test_missing_marker_is_reported():
    assert sft.response_start([1, 2, 3, 4], T) == -1


def test_marker_at_the_very_end_leaves_no_answer():
    ids = [1, 7, 8, 9]
    assert sft.response_start(ids, T) == len(ids)


def test_script_trains_with_the_production_system_prompt():
    class Tok:
        def apply_chat_template(self, messages, tokenize, add_generation_prompt, **kwargs):
            return "|".join(m["role"] + ":" + m["content"] for m in messages)

    text = sft.format_example({"prompt": "q", "completion": "a"}, Tok())
    assert text.startswith("system:" + sft.PRODUCTION_SYSTEM_PROMPT)
    assert text.endswith("assistant:a")
