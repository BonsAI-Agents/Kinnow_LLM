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
    SEED       — random seed (default 42, the Hugging Face default). Train twice with different seeds to see
                 how much a score moves on its own before trusting a small difference between versions.
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

# BASE_MODEL=Qwen/Qwen3-8B trains the Qwen3 candidate; set OUTPUT_DIR and HF_REPO too so the two runs
# do not overwrite each other.
BASE_MODEL = os.getenv("BASE_MODEL", "Qwen/Qwen2.5-7B-Instruct")
HF_REPO = os.getenv("HF_REPO", "KaraPatelDev/kinnow-v1")
# DATA_DIR=data/v2_training trains on the merged set (Tejas's data + our non-conflicting rows)
DATA_DIR = os.getenv("DATA_DIR", "data/v1_training")
TRAIN_PATH = f"{DATA_DIR}/train.jsonl"
VAL_PATH = f"{DATA_DIR}/val.jsonl"
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "models/sft_adapter")
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
    # enable_thinking=False: Qwen3's template otherwise lets the model open a <think> block. The server
    # must send the same flag. Qwen2.5's template ignores it.
    return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False,
                                         enable_thinking=False)


END_TOKEN = "<|im_end|>"


def set_distinct_pad_token(tokenizer) -> None:
    """The pad token must differ from the end-of-turn token.

    The collator sets every label equal to the pad token id to -100. With pad == <|im_end|> (what
    `pad_token = eos_token` gives on Qwen) the end of every answer is masked out of the loss, so the model
    never learns to stop and rambles to the token cap. Found in the first eval (median 205-word answers
    against about 40 in the training data).
    """
    end_id = tokenizer.convert_tokens_to_ids(END_TOKEN)
    if tokenizer.pad_token_id is None or tokenizer.pad_token_id == end_id:
        tokenizer.pad_token = "<|endoftext|>"
    if tokenizer.pad_token_id == end_id or tokenizer.pad_token_id is None:
        raise RuntimeError("Could not pick a pad token different from <|im_end|>.")


def check_end_token_trained(tokenizer, collator, rows: list[dict]) -> None:
    """Fail loudly if <|im_end|> would not carry a loss label for a sample of rows."""
    end_id = tokenizer.convert_tokens_to_ids(END_TOKEN)
    for ex in rows[:8]:
        ids = tokenizer(format_example(ex, tokenizer), add_special_tokens=False)["input_ids"]
        labels = collator([{"input_ids": ids}])["labels"][0].tolist()
        if end_id not in labels:
            raise RuntimeError("<|im_end|> is masked out of the loss: the model would not learn to stop.")
    print(f"  end-of-answer token {END_TOKEN} carries a loss label: OK ({min(8, len(rows))} rows checked)")


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
    # Real bf16 needs an Ampere GPU (compute capability 8+). A T4 is 7.5: recent PyTorch still reports
    # is_bf16_supported() = True there (slow emulation), so check the capability, not that flag.
    use_bf16 = torch.cuda.get_device_capability()[0] >= 8
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
    set_distinct_pad_token(tokenizer)
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
    check_end_token_trained(tokenizer, collator, train_raw)

    # Plan 4d (Kaggle T4x2): effective batch 8, 600 steps is about 2.8 epochs of 1,737 rows
    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        max_steps=int(os.getenv("MAX_STEPS", "600")),
        seed=int(os.getenv("SEED", "42")),
        per_device_train_batch_size=2,
        # The default eval batch size is 8. On a T4 the logits of 8 long sequences (vocab 152k) need
        # more than 3 GiB and crashed the first evaluation (step 100) with CUDA OOM, before any checkpoint.
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_steps=30,
        optim="adamw_8bit",
        fp16=not use_bf16,
        bf16=use_bf16,
        gradient_checkpointing=True,
        logging_steps=10,
        eval_strategy="steps",   # new name (transformers 4.41+); transformers 4.51 for Qwen3 rejects the old evaluation_strategy
        eval_steps=100,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        group_by_length=True,
        report_to="none",                    # set to "wandb" if using W&B
        dataloader_num_workers=2,
        # Do NOT set remove_unused_columns=False: trl 0.11 then keeps the raw "text" column and the
        # collator crashes at step 0 trying to pad it ("excessive nesting"). Found on Kaggle.
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

    # Write down exactly what was used, next to the adapter, so a score can always be traced to its settings
    # (the Kaggle job scripts copy this into the run record). A failure here must never block the upload below.
    try:
        settings = {
            "base_model": BASE_MODEL, "hf_repo": HF_REPO, "precision": "bf16" if use_bf16 else "fp16",
            "seed": training_args.seed, "max_steps": training_args.max_steps,
            "learning_rate": training_args.learning_rate, "lr_scheduler": "cosine",
            "warmup_steps": training_args.warmup_steps, "optimizer": training_args.optim,
            "per_device_batch": training_args.per_device_train_batch_size,
            "gradient_accumulation": training_args.gradient_accumulation_steps,
            "max_seq_length": MAX_SEQ_LENGTH,
            "lora": {"r": lora_config.r, "alpha": lora_config.lora_alpha, "dropout": lora_config.lora_dropout,
                     "target_modules": sorted(lora_config.target_modules)},
            "train_rows": len(train_raw), "val_rows": len(val_raw),
            "eval_loss_history": [[h["step"], round(h["eval_loss"], 4)]
                                  for h in trainer.state.log_history if "eval_loss" in h],
            "best_eval_loss": trainer.state.best_metric,
        }
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(os.path.join(OUTPUT_DIR, "run_settings.json"), "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=1)
    except Exception as e:      # noqa: BLE001
        print("could not write run_settings.json:", e)

    print(f"\nSaving adapter to {OUTPUT_DIR}")
    trainer.save_model(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    print(f"\nPushing to HuggingFace: {HF_REPO}-sft-adapter")
    model.push_to_hub(f"{HF_REPO}-sft-adapter", token=os.getenv("HF_TOKEN"))
    tokenizer.push_to_hub(f"{HF_REPO}-sft-adapter", token=os.getenv("HF_TOKEN"))

    print("SFT training complete.")


if __name__ == "__main__":
    main()
