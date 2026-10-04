#!/usr/bin/env python3
"""Run one seeded Werwolf game with local LLMs (Ollama), full JSONL log.

Usage:
    python scripts/run_werwolf_game.py --model granite4.1:8b --seed 42
    python scripts/run_werwolf_game.py --roster-file my_roster.json
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(line_buffering=True)
from bench_common import ROOT, safe_filename  # noqa: E402
from werwolf import prompts  # noqa: E402
from werwolf.engine import Game  # noqa: E402
from werwolf.player import LLMClient, Player  # noqa: E402

ROLES = ["werwolf", "werwolf", "seer", "witch", "villager", "villager", "villager", "villager"]


def build_players(roster: list[dict], rng: random.Random) -> list[Player]:
    roles = ROLES[:len(roster)]
    rng.shuffle(roles)
    players = []
    for seat, entry in enumerate(roster):
        players.append(Player(
            seat=seat, name=entry["name"], persona=entry["persona"],
            model=entry["model"], role=roles[seat],
        ))
    return players


def load_roster(args) -> list[dict]:
    if args.roster_file:
        roster = json.loads(Path(args.roster_file).read_text(encoding="utf-8"))
    else:
        if not args.model:
            raise SystemExit("Provide --model or --roster-file")
        roster = [{"name": name, "persona": persona, "model": args.model}
                  for name, persona in prompts.PERSONAS]
    if len(roster) != 8:
        raise SystemExit(f"Roster must have exactly 8 players, got {len(roster)}")
    return roster


def execute_game(roster: list[dict], seed: int, model_tag: str,
                 base_url: str = "http://127.0.0.1:11434", max_days: int = 8,
                 temperature: float = 0.7, discussion_rounds: int = 2,
                 timeout: int = 300, verbose: bool = True) -> tuple[str, dict]:
    rng = random.Random(seed)
    players = build_players(roster, rng)

    date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    run_id = f"{date}_werwolf_{model_tag}_seed{seed}"
    out_dir = ROOT / "results" / "werwolf_runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "run_id": run_id, "seed": seed, "base_url": base_url,
        "temperature": temperature, "max_days": max_days,
        "discussion_rounds": discussion_rounds,
        "roster": [{"seat": p.seat, "name": p.name, "persona": p.persona,
                    "model": p.model, "role": p.role} for p in players],
    }
    (out_dir / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False),
                                         encoding="utf-8")

    if verbose:
        print(f"run_id={run_id}")
        print("Roles (GM only):")
        for p in players:
            print(f"  {p.name:8s} {p.role:9s} ({p.model})")

    client = LLMClient(base_url=base_url, timeout=timeout)
    game = Game(players, client, out_dir, seed=seed, max_days=max_days,
                temperature=temperature, discussion_rounds=discussion_rounds,
                verbose=verbose)
    started = time.time()
    summary = game.run()
    elapsed = time.time() - started
    summary["elapsed_seconds"] = round(elapsed, 1)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                          encoding="utf-8")
    if verbose:
        print(f"\n{'='*60}")
        print(f"winner={summary['winner']} days={summary['days']} "
              f"events={summary['events']} role_leaks={summary['role_leaks']} "
              f"invalid_votes={summary['invalid_votes']} refusals={summary['moral_refusals']}")
        print(f"elapsed_seconds={elapsed:.0f}")
        print(f"output_dir={out_dir}")
    return run_id, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Werwolf game with local LLMs.")
    parser.add_argument("--model", help="Use the same model for all 8 seats")
    parser.add_argument("--roster-file", help="JSON: [{name, persona, model}, ...] (8 entries)")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-days", type=int, default=8)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--discussion-rounds", type=int, default=2)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    roster = load_roster(args)
    model_tag = safe_filename(args.model) if args.model else "mixed"
    execute_game(roster, args.seed, model_tag, base_url=args.base_url,
                 max_days=args.max_days, temperature=args.temperature,
                 discussion_rounds=args.discussion_rounds, timeout=args.timeout,
                 verbose=not args.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
