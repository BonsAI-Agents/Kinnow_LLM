"""
Merge the trained LoRA adapter back into the base model weights.
Produces a single standalone model (no PEFT dependency at inference time).

Run after DPO training:
    python training/merge_adapter.py

Output: models/merged/   — full merged model, ready for AWQ quantization.
"""

import os
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
ADAPTER_PATH = "models/dpo_adapter"      # use sft_adapter if skipping DPO
MERGED_OUTPUT = "models/merged"
HF_REPO = os.getenv("HF_REPO", "KaraPatelDev/kinnow-v1")


def main():
    print(f"Loading base model: {BASE_MODEL}")
    tokenizer = AutoTokenizer.from_pretrained(ADAPTER_PATH)

    # Load in fp16 for merging (not 4-bit — merge requires full precision)
    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.float16,
        device_map="cpu",          # merge on CPU to avoid GPU OOM
        trust_remote_code=True,
    )

    print(f"Loading adapter: {ADAPTER_PATH}")
    model = PeftModel.from_pretrained(base_model, ADAPTER_PATH)

    print("Merging adapter into base model weights…")
    model = model.merge_and_unload()

    print(f"Saving merged model to {MERGED_OUTPUT}")
    model.save_pretrained(MERGED_OUTPUT, safe_serialization=True)
    tokenizer.save_pretrained(MERGED_OUTPUT)

    print(f"Pushing merged model to HuggingFace: {HF_REPO}-merged")
    model.push_to_hub(f"{HF_REPO}-merged", token=os.getenv("HF_TOKEN"), safe_serialization=True)
    tokenizer.push_to_hub(f"{HF_REPO}-merged", token=os.getenv("HF_TOKEN"))

    print("Merge complete. Next: run training/quantize_awq.py")


if __name__ == "__main__":
    main()
