"""
Phase 3 — QLoRA Supervised Fine-Tuning (SFT), plan sections 4a-4f.
Trains a LoRA adapter on top of Qwen2.5-7B-Instruct using the ERP dataset.

Run on Kaggle (T4: fp16) or an Ampere GPU (A10G/A100: bf16); precision is auto-detected:
    python training/sft_train.py

Check the data and the loss mask first (no GPU, no model download, only the tokenizer):
    python training/sft_train.py --dry-run

Env vars:
    HF_TOKEN   — HuggingFace write token (only for the final push)
    HF_REPO    — e.g. KaraPatelDev/kinnow-v1
    MAX_STEPS  — override the 600 steps (plan 4d: 800 for 3000+ examples)
"""

import json
import os
import sys
from pathlib import Path

# Train with the exact system prompt the server sends (guardrails Layer 1).
# Plan 4e: "Never train without the system prompt" - otherwise train/serve differ
# and the scope-refusal behaviour does not transfer.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from guardrails.layer1_system_prompt import PRODUCTION_SYSTEM_PROMPT  # noqa: E402

BASE_MODEL = "Qwen/Qwen2.5-7B-Instruct"
HF_REPO = os.getenv("HF_REPO", "KaraPatelDev/kinnow-v1")
TRAIN_PATH = "data/v1_training/train.jsonl"
VAL_PATH = "data/v1_training/val.jsonl"
OUTPUT_DIR = "models/sft_adapter"
MAX_SEQ_LENGTH = 1024

# Qwen chat template: the reply starts right after this marker. Only tokens after it get a loss.
RESPONSE_TEMPLATE = "<|im_start|>assistant\n"


def load_jsonl(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def format_example(ex: dict, tokenizer) -> str:
    """Format as chat template for Qwen2.5."""
    messages = [
        {"role": "system", "content": PRODUCTION_SYSTEM_PROMPT},
        {"role": "user", "content": ex["prompt"]},
        {"role": "assistant", "content": ex["completion"]},
    ]
    return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)


def response_start(input_ids: list[int], template_ids: list[int]) -> int:
    """Index of the first token after the LAST assistant marker, or -1 if the marker is missing."""
    n = len(template_ids)
    for i in range(len(input_ids) - n, -1, -1):
        if input_ids[i:i + n] == template_ids:
            return i + n
    return -1


def check_data(tokenizer, rows: list[dict], name: str) -> dict:
    """Tokenise like training does and report what the loss would be computed on."""
    template_ids = tokenizer.encode(RESPONSE_TEMPLATE, add_special_tokens=False)
    lengths, answer_tokens, missing, truncated, answer_cut = [], [], 0, 0, 0
    for ex in rows:
        ids = tokenizer(format_example(ex, tokenizer), add_special_tokens=False)["input_ids"]
        start = response_start(ids, template_ids)
        lengths.append(len(ids))
        if start < 0:
            missing += 1
            continue
        answer_tokens.append(len(ids) - start)
        if len(ids) > MAX_SEQ_LENGTH:
            truncated += 1
            if start >= MAX_SEQ_LENGTH - 8:      # nothing (or almost nothing) of the answer survives
                answer_cut += 1
    lengths.sort()
    report = {
        "set": name, "rows": len(rows),
        "template_missing": missing,
        "over_max_len": truncated, "answer_lost": answer_cut,
        "tokens_p50": lengths[len(lengths) // 2], "tokens_max": lengths[-1],
        "answer_tokens_mean": round(sum(answer_tokens) / max(1, len(answer_tokens)), 1),
        "prompt_share_pct": round(100 * (1 - sum(answer_tokens) / max(1, sum(lengths))), 1),
    }
    print(f"  {name}: {report}")
    return report


def dry_run() -> int:
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    print(f"Dry run: tokenizer only, max_seq_length={MAX_SEQ_LENGTH}")
    ok = True
    for name, path in (("train", TRAIN_PATH), ("val", VAL_PATH)):
        r = check_data(tokenizer, load_jsonl(path), name)
        if r["template_missing"] or r["answer_lost"]:
            ok = False
    # Show exactly which tokens carry loss for one example
    ex = load_jsonl(TRAIN_PATH)[0]
    ids = tokenizer(format_example(ex, tokenizer), add_special_tokens=False)["input_ids"]
    start = response_start(ids, tokenizer.encode(RESPONSE_TEMPLATE, add_special_tokens=False))
    print("\nLoss is computed on this text only:\n" + repr(tokenizer.decode(ids[start:])))
    print("\n" + ("OK: every example has an answer inside the window." if ok else
                  "PROBLEM: see template_missing / answer_lost above."))
    return 0 if ok else 1


def main():
    if "--dry-run" in sys.argv:
        sys.exit(dry_run())

    import torch
    from datasets import Dataset
    from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
    from transformers import (AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig,
                              TrainingArguments)
    from trl import DataCollatorForCompletionOnlyLM, SFTTrainer

    if not torch.cuda.is_available():
        sys.exit("No GPU found. Run this on Kaggle/Colab (use --dry-run to check the data without one).")
    use_bf16 = torch.cuda.is_bf16_supported()      # T4 is not: it needs fp16 (plan 4d)
    compute_dtype = torch.bfloat16 if use_bf16 else torch.float16
    print(f"Base model: {BASE_MODEL}\nOutput: {OUTPUT_DIR}\nPrecision: {'bf16' if use_bf16 else 'fp16'}")

    # 4-bit quantization config (reduces memory from ~56GB to ~8GB)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
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
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)

    # LoRA config: r=64, alpha=128 (high rank for domain-specific fine-tuning)
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

    # Load, check and format data. Refuse to train if the loss mask would be wrong.
    train_raw, val_raw = load_jsonl(TRAIN_PATH), load_jsonl(VAL_PATH)
    for name, rows in (("train", train_raw), ("val", val_raw)):
        r = check_data(tokenizer, rows, name)
        if r["template_missing"] or r["answer_lost"]:
            sys.exit(f"Aborting: {name} data has examples with no trainable answer (see above).")

    train_ds = Dataset.from_dict({"text": [format_example(ex, tokenizer) for ex in train_raw]})
    val_ds = Dataset.from_dict({"text": [format_example(ex, tokenizer) for ex in val_raw]})

    # Loss only on the assistant reply (plan 4f), not on the system prompt or the question.
    # Token ids, not the string: the tokenizer can split "\n" differently in context.
    collator = DataCollatorForCompletionOnlyLM(
        response_template=tokenizer.encode(RESPONSE_TEMPLATE, add_special_tokens=False),
        tokenizer=tokenizer,
    )

    # Plan 4d (Kaggle T4x2): effective batch 8, 600 steps is about 2.8 epochs of 1,737 rows
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        max_steps=int(os.getenv("MAX_STEPS", "600")),
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_steps=30,
        optim="adamw_8bit",
        fp16=not use_bf16,
        bf16=use_bf16,
        gradient_checkpointing=True,
        logging_steps=10,
        evaluation_strategy="steps",
        eval_steps=100,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        group_by_length=True,
        report_to="none",                    # set to "wandb" if using W&B
        dataloader_num_workers=2,
        remove_unused_columns=False,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        dataset_text_field="text",
        data_collator=collator,
        max_seq_length=MAX_SEQ_LENGTH,
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
