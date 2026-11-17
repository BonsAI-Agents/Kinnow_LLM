"""
Full model eval (plan 6a, 6c, 6e, 6f, 19f, 19g).

Scores a model on the held-out eval sets and checks the v1 exit criteria:
  eval/golden_set.jsonl        single-turn, per category (GST, PAYROLL, INVOICE, REFUSAL)
  eval/hindi_eval_30.jsonl     Hindi, compared against English per category
  eval/multiturn_eval_20.jsonl 3-turn conversations that depend on earlier turns

The model is always called with the production system prompt (the same one the
server sends and sft_train.py trains with).

Usage:
    python eval/run_full_eval.py --self-test                    # sanity-check the sets (no model needed)
    python eval/run_full_eval.py --model-id KaraPatelDev/kinnow-v1
    python eval/run_full_eval.py --model-id Qwen/Qwen2.5-7B-Instruct --tag baseline
    python eval/run_full_eval.py --responses my_responses.jsonl  # score pre-computed responses

--responses file: one JSON object per line, {"key": ..., "response": ...} where key is the
question text, or "<multiturn id>#<turn number>" for multi-turn turns.

Exit code 1 when a v1 target, the Hindi gap, the false-refusal limit or the regression gate fails.
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EVAL_DIR = ROOT / "eval"
RESULTS_DIR = EVAL_DIR / "results"

# v1 exit criteria (plan section 17, Phase 2)
TARGETS = {"overall": 78.0, "GST": 65.0, "PAYROLL": 82.0, "INVOICE": 86.0}
MAX_FALSE_REFUSAL_PCT = 3.0
HINDI_GAP_WARN_PP, HINDI_GAP_BLOCK_PP = 15.0, 25.0
REGRESSION_PP = 5.0

REFUSAL_PHRASES = [
    "i am kinnow's erp assistant and can only help",
    "i can only help with erp",
    "i can only help with gst, payroll",
    "outside my scope",
    "i cannot help with that",
    "i'm not able to help with",
    "that's outside",
    "i don't have information about",
    "not within my area",
    "only assist with",
    "cannot change my role",
    "मैं केवल gst",
]


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"(\d+)\s+percent", r"\1%", text)
    text = re.sub(r"(\d+)\.0%", r"\1%", text)
    # Plan 6a normalisation plus: ignore digit-grouping commas so "25,000", "25000" and
    # Indian "2,00,000" / "200000" all match. Applied to responses and keywords alike.
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    return text


def evaluate_example(response: str, must_contain: list, must_not_contain: list = None) -> dict:
    r = normalize_text(response)
    passed_must = all(normalize_text(mc) in r for mc in must_contain)
    failed_must_not = any(normalize_text(m) in r for m in (must_not_contain or []))
    return {"passed": passed_must and not failed_must_not,
            "passed_must_contain": passed_must, "failed_must_not_contain": failed_must_not}


def load_jsonl(path: Path) -> list:
    if not path.exists():
        print(f"WARNING: {path.relative_to(ROOT)} not found, skipping")
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def pct(n: int, d: int) -> float:
    return round(100 * n / d, 1) if d else 0.0


class Responder:
    """Produces a response for (history, question). Three modes: model, precomputed, self-test."""

    def __init__(self, args):
        self.mode = "selftest" if args.self_test else ("responses" if args.responses else "model")
        self.max_new_tokens = args.max_new_tokens
        self.pre = {}
        if self.mode == "responses":
            for row in load_jsonl(Path(args.responses)):
                self.pre[row["key"]] = row["response"]
        if self.mode == "model":
            import torch
            from transformers import AutoTokenizer, AutoModelForCausalLM
            from guardrails.layer1_system_prompt import PRODUCTION_SYSTEM_PROMPT
            self.system = PRODUCTION_SYSTEM_PROMPT
            self.tok = AutoTokenizer.from_pretrained(args.model_id)
            self.model = AutoModelForCausalLM.from_pretrained(args.model_id, torch_dtype=torch.float16, device_map="auto")
            if args.adapter:
                from peft import PeftModel
                self.model = PeftModel.from_pretrained(self.model, args.adapter)
            self.model.eval()
            self.torch = torch

    def respond(self, key: str, history: list, question: str, reference: str) -> str:
        if self.mode == "selftest":
            return reference
        if self.mode == "responses":
            return self.pre.get(key, "")
        messages = [{"role": "system", "content": self.system}] + history + [{"role": "user", "content": question}]
        ids = self.tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt", return_dict=True)
        ids = {k: v.to(self.model.device) for k, v in ids.items()}
        with self.torch.no_grad():
            out = self.model.generate(**ids, max_new_tokens=self.max_new_tokens, do_sample=False)
        return self.tok.decode(out[0][ids["input_ids"].shape[-1]:], skip_special_tokens=True)


def run_single(resp: Responder, items: list) -> list:
    results = []
    for ex in items:
        t0 = time.time()
        text = resp.respond(ex["question"], [], ex["question"], ex["reference"])
        ms = (time.time() - t0) * 1000
        r = evaluate_example(text, ex["must_contain"], ex.get("must_not_contain"))
        results.append({**ex, "response": text, "passed": r["passed"], "latency_ms": round(ms, 1)})
    return results


def per_category(results: list) -> dict:
    cats = {}
    for r in results:
        cats.setdefault(r["category"], []).append(1 if r["passed"] else 0)
    return {c: pct(sum(v), len(v)) for c, v in cats.items()}


def false_refusal_rate(results: list) -> dict:
    """A false refusal is a refusal phrase on a legitimate (non-REFUSAL) question."""
    legit = [r for r in results if r["category"] != "REFUSAL"]
    bad = [r for r in legit if any(p in r["response"].lower() for p in REFUSAL_PHRASES)]
    return {"false_refusals": len(bad), "legit_total": len(legit), "frr_pct": pct(len(bad), len(legit)),
            "examples": [b["question"] for b in bad[:5]]}


def run_multiturn(resp: Responder, items: list) -> dict:
    convs, turn_total, turn_pass = [], 0, 0
    for ex in items:
        history, ok_all, turns = [], True, []
        for t in ex["conversation"]:
            key = f"{ex['id']}#{t['turn']}"
            text = resp.respond(key, history, t["user"], t.get("reference", ""))
            r = evaluate_example(text, t["must_contain"], t.get("must_not_contain"))
            turns.append({"turn": t["turn"], "passed": r["passed"], "user": t["user"], "response": text[:300]})
            turn_total += 1
            turn_pass += 1 if r["passed"] else 0
            ok_all &= r["passed"]
            history += [{"role": "user", "content": t["user"]}, {"role": "assistant", "content": text}]
        convs.append({"id": ex["id"], "category": ex.get("category"), "all_passed": ok_all, "turns": turns})
    return {"conversations_pass_pct": pct(sum(c["all_passed"] for c in convs), len(convs)),
            "turns_pass_pct": pct(turn_pass, turn_total), "n": len(convs), "results": convs}


def regression_gate(new: dict, prev: dict) -> dict:
    fails = []
    for cat, score in new.items():
        drop = prev.get(cat, 0) - score
        if cat in prev and drop > REGRESSION_PP:
            fails.append({"category": cat, "prev": prev[cat], "new": score, "drop": round(drop, 1)})
    return {"gate_passed": not fails, "failures": fails}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-id")
    ap.add_argument("--adapter", help="optional LoRA adapter path/repo applied on top of --model-id")
    ap.add_argument("--responses")
    ap.add_argument("--self-test", action="store_true", help="answer every item with its own reference")
    ap.add_argument("--tag", default="", help="label for this run, e.g. baseline or v1")
    ap.add_argument("--max-new-tokens", type=int, default=300)
    args = ap.parse_args()
    if not (args.self_test or args.responses or args.model_id):
        ap.error("give --model-id, --responses or --self-test")

    golden = load_jsonl(EVAL_DIR / "golden_set.jsonl")
    hindi = load_jsonl(EVAL_DIR / "hindi_eval_30.jsonl")
    multi = load_jsonl(EVAL_DIR / "multiturn_eval_20.jsonl")
    resp = Responder(args)

    gres = run_single(resp, golden)
    hres = run_single(resp, hindi)
    mres = run_multiturn(resp, multi)

    cats = per_category(gres)
    overall = pct(sum(r["passed"] for r in gres), len(gres))
    lat = sorted(r["latency_ms"] for r in gres) or [0]
    frr = false_refusal_rate(gres)
    hcats = per_category(hres)
    h_overall = pct(sum(r["passed"] for r in hres), len(hres))
    gap = round(overall - h_overall, 1)

    summary = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "model": args.model_id or ("self-test" if args.self_test else "precomputed"),
        "tag": args.tag, "mode": resp.mode,
        "overall": overall, "per_category": cats,
        "latency_p50_ms": lat[len(lat) // 2], "latency_p95_ms": lat[int(len(lat) * 0.95)],
        "false_refusal_rate_pct": frr["frr_pct"], "n_golden": len(gres),
        "hindi_overall": h_overall, "hindi_per_category": hcats, "hindi_gap_pp": gap,
        "multiturn_conversations_pass_pct": mres["conversations_pass_pct"],
        "multiturn_turns_pass_pct": mres["turns_pass_pct"],
    }

    problems = []
    for name, target in TARGETS.items():
        got = overall if name == "overall" else cats.get(name)
        if got is not None and got < target:
            problems.append(f"{name} {got}% < target {target}%")
    if frr["frr_pct"] > MAX_FALSE_REFUSAL_PCT:
        problems.append(f"false refusal rate {frr['frr_pct']}% > {MAX_FALSE_REFUSAL_PCT}%")
    if hindi and gap > HINDI_GAP_BLOCK_PP:
        problems.append(f"Hindi {gap}pp below English (block threshold {HINDI_GAP_BLOCK_PP}pp)")
    elif hindi and gap > HINDI_GAP_WARN_PP:
        print(f"WARNING: Hindi is {gap}pp below English (warn threshold {HINDI_GAP_WARN_PP}pp)")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    hist = RESULTS_DIR / "eval_history.jsonl"
    prev = None
    if hist.exists() and args.tag != "selftest" and not args.self_test:
        rows = [json.loads(l) for l in open(hist, encoding="utf-8") if l.strip()]
        rows = [r for r in rows if r.get("mode") != "selftest"]
        prev = rows[-1] if rows else None
    if prev:
        gate = regression_gate({**cats, "overall": overall}, {**prev["per_category"], "overall": prev["overall"]})
        summary["regression_gate"] = gate
        for f in gate["failures"]:
            problems.append(f"regression {f['category']}: {f['prev']}% -> {f['new']}% (-{f['drop']}pp)")

    summary["passed"] = not problems
    summary["problems"] = problems
    with open(RESULTS_DIR / "full_eval.json", "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "golden": gres, "hindi": hres, "multiturn": mres,
                   "false_refusals": frr}, f, ensure_ascii=False, indent=1)
    with open(hist, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, ensure_ascii=False) + "\n")

    print(f"\n{'=' * 60}\n  Full eval ({resp.mode}{', ' + args.tag if args.tag else ''})\n{'=' * 60}")
    print(f"  overall        : {overall}%   (target {TARGETS['overall']}%)   n={len(gres)}")
    for c in sorted(cats):
        t = TARGETS.get(c)
        print(f"  {c:<14} : {cats[c]}%" + (f"   (target {t}%)" if t else ""))
    print(f"  false refusals : {frr['frr_pct']}% ({frr['false_refusals']}/{frr['legit_total']})   (limit {MAX_FALSE_REFUSAL_PCT}%)")
    print(f"  hindi          : {h_overall}% (gap {gap}pp vs English)  " + str(hcats))
    print(f"  multi-turn     : {mres['conversations_pass_pct']}% of conversations, {mres['turns_pass_pct']}% of turns")
    print(f"  latency        : p50 {summary['latency_p50_ms']}ms, p95 {summary['latency_p95_ms']}ms")
    print("\n  " + ("PASSED" if not problems else "FAILED"))
    for p in problems:
        print("   -", p)
    sys.exit(0 if not problems else 1)


if __name__ == "__main__":
    main()
