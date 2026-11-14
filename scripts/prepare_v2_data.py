"""
Merge human-reviewed feedback into a new training JSONL for v2 fine-tuning.
Only includes items where the reviewer set 'include': true and provided a corrected completion.

Usage:
    python scripts/prepare_v2_data.py data/production_reviewed/batch_01.jsonl \
        --existing data/v1_training/train.jsonl \
        --output data/v1_training/train_v2.jsonl

The output file contains all v1 examples + accepted reviewed examples (deduplicated).
"""

import json
import argparse
from pathlib import Path


def load_jsonl(path: str) -> list[dict]:
    items = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def prepare(reviewed_path: str, existing_path: str | None, output_path: str):
    reviewed = load_jsonl(reviewed_path)

    accepted = []
    skipped_no_flag = 0
    skipped_empty = 0

    for item in reviewed:
        if item.get('include') is not True:
            skipped_no_flag += 1
            continue
        corrected = item.get('corrected_completion', '').strip()
        query = item.get('query', '').strip()
        if not corrected or not query:
            skipped_empty += 1
            continue
        accepted.append({
            'domain': item.get('domain', 'ERP'),
            'prompt': query,
            'completion': corrected,
        })

    # Load existing training data
    existing = []
    if existing_path and Path(existing_path).exists():
        existing = load_jsonl(existing_path)

    # Deduplicate by prompt
    seen = {ex['prompt'].strip().lower() for ex in existing}
    new_examples = [ex for ex in accepted if ex['prompt'].strip().lower() not in seen]

    combined = existing + new_examples

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        for ex in combined:
            f.write(json.dumps(ex, ensure_ascii=False) + '\n')

    print(f"\nV2 data preparation complete:")
    print(f"  Reviewed items  : {len(reviewed)}")
    print(f"  Accepted        : {len(accepted)}")
    print(f"  New (deduplicated): {len(new_examples)}")
    print(f"  Skipped (no include flag): {skipped_no_flag}")
    print(f"  Skipped (empty completion): {skipped_empty}")
    print(f"  Existing examples: {len(existing)}")
    print(f"  Total v2 dataset : {len(combined)}")
    print(f"  Output → {out}")
    print(f"\nNext: run scripts/validate_data.py {out}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('reviewed', help='Path to human-reviewed JSONL')
    parser.add_argument('--existing', default='data/v1_training/train.jsonl',
                        help='Existing training data to merge with')
    parser.add_argument('--output', default='data/v1_training/train_v2.jsonl')
    args = parser.parse_args()
    prepare(args.reviewed, args.existing, args.output)
