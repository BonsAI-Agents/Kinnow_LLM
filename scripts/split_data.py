"""
Split a validated JSONL file into train and val sets.
Stratified by domain so each split has proportional domain coverage.

Usage:
    python scripts/split_data.py data/v1_training/raw.jsonl --val-ratio 0.1
Outputs:
    data/v1_training/train.jsonl
    data/v1_training/val.jsonl
"""

import json
import random
import argparse
from collections import defaultdict
from pathlib import Path


def split_file(input_path: str, val_ratio: float = 0.1, seed: int = 42):
    p = Path(input_path)
    out_dir = p.parent

    # Load all examples grouped by domain
    by_domain: dict[str, list[dict]] = defaultdict(list)
    with open(p, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            by_domain[obj['domain']].append(obj)

    rng = random.Random(seed)
    train_examples = []
    val_examples = []

    for domain, examples in by_domain.items():
        rng.shuffle(examples)
        n_val = max(1, int(len(examples) * val_ratio))
        val_examples.extend(examples[:n_val])
        train_examples.extend(examples[n_val:])

    # Shuffle final lists
    rng.shuffle(train_examples)
    rng.shuffle(val_examples)

    train_path = out_dir / 'train.jsonl'
    val_path = out_dir / 'val.jsonl'

    with open(train_path, 'w', encoding='utf-8') as f:
        for ex in train_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + '\n')

    with open(val_path, 'w', encoding='utf-8') as f:
        for ex in val_examples:
            f.write(json.dumps(ex, ensure_ascii=False) + '\n')

    print(f"\nSplit complete:")
    print(f"  Train : {len(train_examples)} examples → {train_path}")
    print(f"  Val   : {len(val_examples)} examples → {val_path}")
    print(f"\n  Domain breakdown (train / val):")
    from collections import Counter
    train_counts = Counter(e['domain'] for e in train_examples)
    val_counts = Counter(e['domain'] for e in val_examples)
    for domain in sorted(by_domain.keys()):
        print(f"    {domain:<10}  train={train_counts[domain]}  val={val_counts[domain]}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('input', help='Path to raw JSONL file')
    parser.add_argument('--val-ratio', type=float, default=0.1, help='Fraction for validation (default 0.1)')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    split_file(args.input, args.val_ratio, args.seed)
