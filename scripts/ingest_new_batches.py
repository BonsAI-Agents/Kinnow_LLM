"""Check and clean the new data batches from Tejas before they are used for training.

Usage:
    python scripts/ingest_new_batches.py <folder with batch*.jsonl> [--keep-check] [--prior <folder of earlier batches>]...

Reads the batch files (training rows in batches 1-14, knowledge notes in 15, glossary in 16) and writes, to data/tejas/new_v3/:
    sft_rows.jsonl      accepted training rows {domain, prompt, completion}
    kb_notes.jsonl      accepted knowledge notes
    glossary.jsonl      glossary entries
    rejected.jsonl      every rejected row with the reason
    report.json         counts per batch and per reason
A row is rejected when: it is not valid JSON or lacks a field; it is marked confidence "check" (unless --keep-check);
the answer is empty or very short; its prompt repeats an earlier prompt (in the batches or in the current training data);
it is too close to a test question (so the score would be inflated); it is too close to a row in an earlier batch (--prior);
or it states the old 24% for Section 50(3).
"""

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("KINNOW_INGEST_OUT", ROOT / "data" / "tejas" / "new_v3"))
DOMAINS = {"GST", "PAYROLL", "INVOICE", "REFUSAL"}
OVERLAP = 0.5            # share of words in common (shared / all distinct words) above which a row counts as a copy of a test question
PRIOR_OVERLAP = 0.6           # share of words in common with a prompt from an earlier batch above which a row counts as a repeat
OVERLAP_WITH_NUMBERS = 0.35   # lower bar when the row also repeats two or more of the test question's figures


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s%]", " ", s.lower())).strip()


def words(s: str) -> set:
    return {w for w in norm(s).split() if len(w) > 2}


def overlap(a: set, b: set) -> float:
    return len(a & b) / max(1, len(a | b))


def figures(s: str) -> set:
    return set(re.findall(r"\d[\d,]*", s))


def load_jsonl(path: Path) -> list:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(line)
    return rows


def test_questions() -> list:
    out = []
    for name in ("golden_set.jsonl", "hindi_eval_30.jsonl", "multiturn_eval_20.jsonl", "fact_checks.jsonl"):
        p = ROOT / "eval" / name
        if not p.exists():
            continue
        for line in load_jsonl(p):
            d = json.loads(line)
            text = d.get("question") or d.get("claim") or ""
            if text:
                out.append((words(text), figures(text)))
            for turn in d.get("conversation", []):          # multi-turn set: every user turn is a test question
                if turn.get("user"):
                    out.append((words(turn["user"]), figures(turn["user"])))
    return out


def existing_prompts() -> set:
    seen = set()
    for p in [ROOT / "data" / "v2_training" / "raw.jsonl", ROOT / "data" / "tejas" / "kinnow_sft_500_v2.jsonl",
              ROOT / "data" / "tejas" / "kinnow_sft_payroll_invoice_v2.jsonl"]:
        if p.exists():
            for line in load_jsonl(p):
                try:
                    seen.add(norm(json.loads(line)["prompt"]))
                except (ValueError, KeyError):
                    pass
    return seen


def prior_prompts(folders: list) -> list:
    """Word sets of every prompt in the earlier batches (batch*.jsonl, and the rows files this script writes)."""
    out = []
    for folder in folders:
        for path in Path(folder).glob("*.jsonl"):
            for line in load_jsonl(path):
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if isinstance(d.get("prompt"), str):
                    out.append(words(d["prompt"]))
    return out


OLD_50_3 = re.compile(r"50\(3\)[^.]{0,120}24\s?%|24\s?%[^.]{0,120}50\(3\)")


def check_sft(d: dict, seen: set, tests: list, keep_check: bool, prior: list = ()):
    for k in ("domain", "prompt", "completion"):
        if not isinstance(d.get(k), str) or not d[k].strip():
            return f"missing {k}"
    if d["domain"] not in DOMAINS:
        return "unknown domain"
    if d.get("confidence") == "check" and not keep_check:
        return "marked check"
    if len(d["completion"].split()) < 15:
        return "answer too short"
    if OLD_50_3.search(d["completion"]):
        return "old 24% for Section 50(3)"
    n = norm(d["prompt"])
    if n in seen:
        return "repeated prompt"
    w, f = words(d["prompt"]), figures(d["prompt"])
    for tw, tf in tests:
        o = overlap(w, tw)
        if o >= OVERLAP or (o >= OVERLAP_WITH_NUMBERS and len(f & tf) >= 2):
            return "too close to a test question"
    if any(overlap(w, pw) >= PRIOR_OVERLAP for pw in prior):
        return "too close to an earlier batch"
    return None


def main():
    argv = sys.argv[1:]
    prior_dirs = [argv[i + 1] for i, a in enumerate(argv) if a == "--prior" and i + 1 < len(argv)]
    args = [a for i, a in enumerate(argv) if not a.startswith("--") and not (i > 0 and argv[i - 1] == "--prior")]
    if not args:
        sys.exit(__doc__)
    keep_check = "--keep-check" in sys.argv
    prior = prior_prompts(prior_dirs)
    tests, seen = test_questions(), existing_prompts()
    sft, notes, gloss, rejected = [], [], [], []
    per_batch = {}
    for path in sorted(Path(args[0]).glob("batch*.jsonl")):
        num = int(re.search(r"batch(\d+)", path.name).group(1))
        c = Counter()
        for line in load_jsonl(path):
            try:
                d = json.loads(line)
            except ValueError:
                rejected.append({"batch": num, "reason": "not valid JSON", "row": line[:200]})
                c["rejected"] += 1
                continue
            if num == 15:
                ok = all(isinstance(d.get(k), str) and d[k].strip() for k in ("domain", "topic", "note", "citation"))
                if ok and d.get("confidence") != "check":
                    notes.append(d)
                    c["accepted"] += 1
                else:
                    rejected.append({"batch": num, "reason": "bad or unchecked note", "row": d})
                    c["rejected"] += 1
            elif num == 16:
                if isinstance(d.get("term"), str) and isinstance(d.get("full"), str):
                    gloss.append(d)
                    c["accepted"] += 1
                else:
                    rejected.append({"batch": num, "reason": "bad glossary entry", "row": d})
                    c["rejected"] += 1
            else:
                why = check_sft(d, seen, tests, keep_check, prior)
                if why:
                    rejected.append({"batch": num, "reason": why, "row": d})
                    c["rejected"] += 1
                else:
                    seen.add(norm(d["prompt"]))
                    sft.append({"domain": d["domain"], "prompt": d["prompt"], "completion": d["completion"]})
                    c["accepted"] += 1
        per_batch[path.name] = dict(c)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in (("sft_rows", sft), ("kb_notes", notes), ("glossary", gloss), ("rejected", rejected)):
        with open(OUT / f"{name}.jsonl", "w", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    report = {"accepted_training_rows": len(sft), "notes": len(notes), "glossary": len(gloss), "rejected": len(rejected),
              "rejected_by_reason": dict(Counter(r["reason"] for r in rejected)), "per_batch": per_batch}
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
