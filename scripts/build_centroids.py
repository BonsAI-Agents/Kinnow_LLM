"""
Build embedding centroids for the Layer 2 classifier from training data.
Run this once after the training data is ready, before starting the API server.
Centroids are saved to data/centroids.npz and loaded at server startup.

Usage:
    python scripts/build_centroids.py data/v1_training/train.jsonl
Output:
    data/centroids.npz   — numpy file with {domain: centroid_vector}
"""

import json
import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from guardrails.layer2_classifier import save_centroids  # noqa: E402


def build_and_save(train_path: str, output_path: str = 'data/centroids.npz'):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("ERROR: sentence-transformers not installed. Run: pip install sentence-transformers")
        return

    print("Loading embedding model…")
    model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')

    # Load prompts grouped by domain
    by_domain: dict[str, list[str]] = defaultdict(list)
    with open(train_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            # Centroids describe what IN-scope queries look like. REFUSAL rows are
            # out-of-scope prompts: as a centroid they would make off-topic queries
            # score as "similar to a domain" and pass Layer 2.
            if obj['domain'] == 'REFUSAL':
                continue
            by_domain[obj['domain']].append(obj['prompt'])

    print(f"Building centroids for {len(by_domain)} domains:")
    centroids = {}
    for domain, prompts in by_domain.items():
        print(f"  {domain}: {len(prompts)} prompts…", end=' ', flush=True)
        embeddings = model.encode(prompts, show_progress_bar=False, batch_size=64)
        centroids[domain] = embeddings.mean(axis=0)
        print("done")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    save_centroids(centroids, out)
    print(f"\nCentroids saved to {out}")
    print("Load at server startup with:")
    print("  from guardrails.layer2_classifier import set_domain_centroids, load_centroids")
    print("  centroids = load_centroids('data/centroids.npz')")
    print("  set_domain_centroids(centroids)")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('train_path', help='Path to train.jsonl')
    parser.add_argument('--output', default='data/centroids.npz')
    args = parser.parse_args()
    build_and_save(args.train_path, args.output)
