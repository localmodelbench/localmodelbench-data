#!/usr/bin/env python3
"""Run N seeded Werwolf games back-to-back and write a batch manifest.

Usage:
    python scripts/run_werwolf_batch.py --roster-file scripts/werwolf/roster_mixed_v1.json \
        --games 20 --seed-start 100 --batch-tag mixed_v1
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(line_buffering=True)

from bench_common import ROOT, safe_filename  # noqa: E402
from run_werwolf_game import execute_game, load_roster  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a batch of Werwolf games.")
    parser.add_argument("--model", help="Same model for all 8 seats")
    parser.add_argument("--roster-file", help="JSON roster (8 entries)")
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--seed-start", type=int, default=100)
    parser.add_argument("--batch-tag", default=None, help="Manifest name suffix")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--max-days", type=int, default=8)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--discussion-rounds", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    roster = load_roster(args)
    model_tag = safe_filename(args.model) if args.model else "mixed"
    batch_tag = args.batch_tag or model_tag

    started = time.time()
    results = []
    for i in range(args.games):
        seed = args.seed_start + i
        print(f"\n[{i + 1}/{args.games}] game seed={seed} …", flush=True)
        try:
            run_id, summary = execute_game(
                roster, seed, model_tag, base_url=args.base_url,
                max_days=args.max_days, temperature=args.temperature,
                discussion_rounds=args.discussion_rounds, timeout=args.timeout,
                verbose=False,
            )
            results.append({"run_id": run_id, "seed": seed, "ok": True, **{
                k: summary[k] for k in ("winner", "days", "events", "role_leaks",
                                        "invalid_votes", "moral_refusals", "elapsed_seconds")}})
            print(f"    -> {summary['winner']} in {summary['days']}d, "
                  f"{summary['elapsed_seconds']:.0f}s, "
                  f"leaks={summary['role_leaks']} inv={summary['invalid_votes']}", flush=True)
        except Exception:
            results.append({"seed": seed, "ok": False,
                            "error": traceback.format_exc(limit=3)})
            print(f"    -> FAILED (see manifest)", flush=True)
            traceback.print_exc(limit=3)

    elapsed = time.time() - started
    manifest = {
        "batch_tag": batch_tag,
        "started": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ"),
        "games_requested": args.games,
        "games_ok": sum(1 for r in results if r.get("ok")),
        "elapsed_seconds": round(elapsed, 1),
        "roster": roster,
        "results": results,
    }
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    out = ROOT / "results" / "werwolf_runs" / f"batch_{stamp}_{safe_filename(batch_tag)}.json"
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    wins = {}
    for r in results:
        if r.get("ok"):
            wins[r["winner"]] = wins.get(r["winner"], 0) + 1
    print(f"\nBatch done: {manifest['games_ok']}/{args.games} games, "
          f"winners={wins}, {elapsed/60:.0f} min")
    print(f"manifest={out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
