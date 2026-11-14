"""
Export thumbs-down feedback from Redis for human review (data flywheel, Section 24).
Outputs a JSONL file that the reviewer fills with corrected completions,
then feeds into prepare_v2_data.py.

Usage:
    python scripts/export_feedback.py --limit 200 --output data/production_reviewed/batch_01.jsonl
"""

import json
import argparse
import asyncio
from datetime import datetime
from pathlib import Path

import redis.asyncio as aioredis
from dotenv import load_dotenv
import os

load_dotenv()


async def export(limit: int, output_path: str):
    r = aioredis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379/0'), decode_responses=True)

    try:
        raw_items = await r.lrange('feedback:queue', 0, limit - 1)
    finally:
        await r.aclose()

    if not raw_items:
        print("No feedback items in queue.")
        return

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    exported = 0
    with open(out, 'w', encoding='utf-8') as f:
        for raw in raw_items:
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue

            # Export format for human reviewer:
            # They fill in 'corrected_completion' and set 'include': true/false
            export_item = {
                'query': item.get('query', ''),
                'bad_response': item.get('response', ''),
                'corrected_completion': '',  # reviewer fills this in
                'include': None,             # reviewer sets true/false
                'exported_at': datetime.utcnow().isoformat(),
            }
            f.write(json.dumps(export_item, ensure_ascii=False) + '\n')
            exported += 1

    print(f"Exported {exported} feedback items to {out}")
    print(f"Next step: open {out} and fill in 'corrected_completion' for each item,")
    print(f"then run: python scripts/prepare_v2_data.py {out}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=200, help='Max items to export')
    parser.add_argument('--output', default=None,
                        help='Output path (default: data/production_reviewed/batch_YYYYMMDD.jsonl)')
    args = parser.parse_args()
    output = args.output or f'data/production_reviewed/batch_{datetime.now().strftime("%Y%m%d")}.jsonl'
    asyncio.run(export(args.limit, output))
