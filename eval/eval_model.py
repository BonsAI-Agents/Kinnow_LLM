"""
Post-training model quality eval gate — Section 22.
Runs after SFT/DPO training. The model must beat the baseline score
on a held-out eval set before the adapter is accepted.

Baseline (Qwen2.5-7B-Instruct before fine-tuning): ~45% exact domain match.
Target after fine-tuning: > 70%.

Usage:
    python eval/eval_model.py --model-id KaraPatelDev/kinnow-v1
    python eval/eval_model.py --model-id KaraPatelDev/kinnow-v1 --baseline 0.45 --threshold 0.70
"""

import json
import argparse
from pathlib import Path

BASELINE_SCORE = 0.45
PASS_THRESHOLD = 0.70

EVAL_CASES = [
    {
        "domain": "GST",
        "prompt": "What is the GST rate on restaurant services?",
        "expected_keywords": ["5%", "SAC", "996331"],
    },
    {
        "domain": "GST",
        "prompt": "What is the GST rate on software development services?",
        "expected_keywords": ["18%", "SAC", "998314"],
    },
    {
        "domain": "GST",
        "prompt": "When is GSTR-3B due for monthly filers?",
        "expected_keywords": ["20th"],
    },
    {
        "domain": "PAYROLL",
        "prompt": "What percentage of salary is deducted for PF?",
        "expected_keywords": ["12%"],
    },
    {
        "domain": "PAYROLL",
        "prompt": "What is the TDS section for salary income?",
        "expected_keywords": ["192"],
    },
    {
        "domain": "GST",
        "prompt": "What is the composition scheme turnover limit?",
        "expected_keywords": ["1.5 crore", "crore"],
    },
    {
        "domain": "INVOICE",
        "prompt": "What is GSTR-2B used for?",
        "expected_keywords": ["reconcil", "ITC", "purchase"],
    },
    {
        "domain": "GST",
        "prompt": "What is the GST rate on packaged food?",
        "expected_keywords": ["5%", "12%", "18%"],
    },
    {
        "domain": "PAYROLL",
        "prompt": "How is gratuity calculated?",
        "expected_keywords": ["15", "26", "basic"],
    },
    {
        "domain": "GST",
        "prompt": "What does ITC stand for in GST?",
        "expected_keywords": ["Input Tax Credit"],
    },
]


def score_response(response: str, expected_keywords: list[str]) -> float:
    """
    Keyword hit rate: fraction of expected keywords found in response.
    Case-insensitive partial match.
    """
    response_lower = response.lower()
    hits = sum(1 for kw in expected_keywords if kw.lower() in response_lower)
    return hits / len(expected_keywords)


def run_eval(model_id: str, baseline: float, threshold: float) -> dict:
    try:
        from transformers import AutoTokenizer, AutoModelForCausalLM
        import torch
    except ImportError:
        print("ERROR: transformers/torch not installed.")
        raise SystemExit(1)

    print(f"Loading model: {model_id}")
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=torch.float16,
        device_map='auto',
    )
    model.eval()

    scores = []
    for case in EVAL_CASES:
        messages = [
            {"role": "user", "content": case["prompt"]},
        ]
        input_ids = tokenizer.apply_chat_template(
            messages, return_tensors="pt", add_generation_prompt=True
        ).to(model.device)

        with torch.no_grad():
            output_ids = model.generate(
                input_ids,
                max_new_tokens=256,
                do_sample=False,   # greedy — deterministic eval results
            )

        response = tokenizer.decode(
            output_ids[0][input_ids.shape[-1]:], skip_special_tokens=True
        )
        score = score_response(response, case["expected_keywords"])
        scores.append(score)
        print(f"  [{case['domain']}] {case['prompt'][:60]!r} → score={score:.2f}")

    avg_score = sum(scores) / len(scores)
    passed = avg_score >= threshold

    result = {
        'model_id': model_id,
        'avg_score': avg_score,
        'baseline': baseline,
        'threshold': threshold,
        'passed': passed,
        'per_case_scores': scores,
    }

    out = Path('eval/results')
    out.mkdir(parents=True, exist_ok=True)
    with open(out / 'model_eval.json', 'w') as f:
        json.dump(result, f, indent=2)

    print(f"\n{'='*55}")
    print(f"  Model Eval Results")
    print(f"{'='*55}")
    print(f"  Model     : {model_id}")
    print(f"  Score     : {avg_score:.2%}  (baseline {baseline:.2%}, threshold {threshold:.2%})")
    print(f"  {'PASSED ✓' if passed else 'FAILED ✗ — score below threshold'}\n")

    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model-id', required=True)
    parser.add_argument('--baseline', type=float, default=BASELINE_SCORE)
    parser.add_argument('--threshold', type=float, default=PASS_THRESHOLD)
    args = parser.parse_args()

    result = run_eval(args.model_id, args.baseline, args.threshold)
    raise SystemExit(0 if result['passed'] else 1)
