"""
Validate a training JSONL file before use.
Checks: schema, domain values, length bounds, duplicates, language consistency.

Usage:
    python scripts/validate_data.py data/v1_training/train.jsonl
"""

import json
import sys
import re
from collections import Counter
from pathlib import Path

VALID_DOMAINS = {"GST", "PAYROLL", "INVOICE", "ERP"}
MIN_PROMPT = 10
MAX_PROMPT = 300
MIN_COMPLETION = 30
MAX_COMPLETION = 600

UNCERTAINTY_PHRASES = [
    r'\bi think\b', r'\bi believe\b', r'\bprobably\b', r'\bmight be\b',
    r'\bi\'m not sure\b', r'\bmaybe\b', r'\bi guess\b',
]

HINDI_RANGE = re.compile(r'[ऀ-ॿ]')


def check_language_consistency(prompt: str, completion: str) -> bool:
    """Returns True if both are in the same language (both Hindi or both Latin)."""
    prompt_hindi = bool(HINDI_RANGE.search(prompt))
    completion_hindi = bool(HINDI_RANGE.search(completion))
    return prompt_hindi == completion_hindi


def validate_file(path: str) -> bool:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: File not found: {path}")
        return False

    errors = []
    warnings = []
    seen_prompts = set()
    domain_counts = Counter()
    total = 0

    with open(p, encoding='utf-8') as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            total += 1

            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"Line {lineno}: invalid JSON — {e}")
                continue

            # Required fields
            for field in ('domain', 'prompt', 'completion'):
                if field not in obj:
                    errors.append(f"Line {lineno}: missing field '{field}'")

            if 'domain' not in obj or 'prompt' not in obj or 'completion' not in obj:
                continue

            domain = obj['domain']
            prompt = obj['prompt']
            completion = obj['completion']

            # Domain
            if domain not in VALID_DOMAINS:
                errors.append(f"Line {lineno}: invalid domain '{domain}' (must be one of {VALID_DOMAINS})")
            else:
                domain_counts[domain] += 1

            # Length
            if len(prompt) < MIN_PROMPT:
                errors.append(f"Line {lineno}: prompt too short ({len(prompt)} chars, min {MIN_PROMPT})")
            if len(prompt) > MAX_PROMPT:
                warnings.append(f"Line {lineno}: prompt long ({len(prompt)} chars, max {MAX_PROMPT})")
            if len(completion) < MIN_COMPLETION:
                errors.append(f"Line {lineno}: completion too short ({len(completion)} chars, min {MIN_COMPLETION})")
            if len(completion) > MAX_COMPLETION:
                warnings.append(f"Line {lineno}: completion long ({len(completion)} chars, max {MAX_COMPLETION})")

            # Duplicate prompts
            norm_prompt = prompt.strip().lower()
            if norm_prompt in seen_prompts:
                warnings.append(f"Line {lineno}: duplicate prompt — '{prompt[:60]}…'")
            seen_prompts.add(norm_prompt)

            # Uncertainty phrases
            comp_lower = completion.lower()
            for phrase_pat in UNCERTAINTY_PHRASES:
                if re.search(phrase_pat, comp_lower):
                    errors.append(f"Line {lineno}: uncertain language in completion ('{phrase_pat}')")
                    break

            # Language consistency
            if not check_language_consistency(prompt, completion):
                warnings.append(f"Line {lineno}: language mismatch — prompt and completion appear to be in different languages")

    # Report
    print(f"\n{'='*55}")
    print(f"  Validation report: {p.name}")
    print(f"{'='*55}")
    print(f"  Total examples : {total}")
    print(f"  Domain breakdown:")
    for domain in sorted(VALID_DOMAINS):
        count = domain_counts.get(domain, 0)
        bar = '█' * (count // 10)
        print(f"    {domain:<10} {count:>4}  {bar}")

    if warnings:
        print(f"\n  Warnings ({len(warnings)}):")
        for w in warnings[:20]:
            print(f"    ⚠  {w}")
        if len(warnings) > 20:
            print(f"    … and {len(warnings) - 20} more")

    if errors:
        print(f"\n  Errors ({len(errors)}) — fix before training:")
        for e in errors[:30]:
            print(f"    ✗  {e}")
        if len(errors) > 30:
            print(f"    … and {len(errors) - 30} more")
        print(f"\n  RESULT: FAILED — {len(errors)} error(s) must be fixed\n")
        return False

    print(f"\n  RESULT: PASSED ✓  ({len(warnings)} warning(s))\n")
    return True


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python scripts/validate_data.py <path_to_jsonl>")
        sys.exit(1)
    ok = validate_file(sys.argv[1])
    sys.exit(0 if ok else 1)
