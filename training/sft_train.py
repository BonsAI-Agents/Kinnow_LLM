"""
Phase 3 — QLoRA Supervised Fine-Tuning (SFT).
Trains a LoRA adapter on top of Qwen2.5-7B-Instruct using the ERP dataset.

Run on Kaggle (A100 40GB):
    python training/sft_train.py

Env vars required:
    HF_TOKEN   — HuggingFace write token
    HF_REPO    — e.g. KaraPatelDev/kinnow-v1
"""

import os
import json
from pathlib import Path

import torch
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
HF_REPO = os.getenv("HF_REPO", "KaraPatelDev/kinnow-v1")
TRAIN_PATH = "data/v1_training/train.jsonl"
VAL_PATH = "data/v1_training/val.jsonl"
OUTPUT_DIR = "models/sft_adapter"


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def format_example(ex: dict, tokenizer) -> str:
    """Format as chat template for Qwen2.5."""
    messages = [
        {"role": "user", "content": ex["prompt"]},
        {"role": "assistant", "content": ex["completion"]},
    ]
    return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)


def main():
    print(f"Base model: {BASE_MODEL}")
    print(f"Output: {OUTPUT_DIR}")

    # 4-bit quantization config (reduces memory from ~56GB to ~8GB)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model.config.use_cache = False

    # LoRA config: r=64, α=128 (high rank for domain-specific fine-tuning)
    lora_config = LoraConfig(
        r=64,
        lora_alpha=128,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # Load and format data
    train_raw = load_jsonl(TRAIN_PATH)
    val_raw = load_jsonl(VAL_PATH)

    train_texts = [format_example(ex, tokenizer) for ex in train_raw]
    val_texts = [format_example(ex, tokenizer) for ex in val_raw]

    train_ds = Dataset.from_dict({"text": train_texts})
    val_ds = Dataset.from_dict({"text": val_texts})

    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        num_train_epochs=3,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,       # effective batch = 16
        warmup_ratio=0.05,
        learning_rate=2e-4,
        fp16=False,
        bf16=True,
        logging_steps=10,
        evaluation_strategy="steps",
        eval_steps=50,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        report_to="none",                    # set to "wandb" if using W&B
        dataloader_num_workers=2,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        dataset_text_field="text",
        max_seq_length=1024,
        args=training_args,
        packing=False,
    )

    print("\nStarting SFT training…")
    trainer.train()

    print(f"\nSaving adapter to {OUTPUT_DIR}")
    trainer.save_model(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    print(f"\nPushing to HuggingFace: {HF_REPO}-sft-adapter")
    model.push_to_hub(f"{HF_REPO}-sft-adapter", token=os.getenv("HF_TOKEN"))
    tokenizer.push_to_hub(f"{HF_REPO}-sft-adapter", token=os.getenv("HF_TOKEN"))

    print("SFT training complete.")


if __name__ == "__main__":
    main()
