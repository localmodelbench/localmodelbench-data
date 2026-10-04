#!/usr/bin/env python3
"""Aggregate Werwolf run results into a per-model table ("Lügen-Rangliste").

Reads every results/werwolf_runs/<run_id>/{config,summary,game.jsonl} and
prints a markdown table + writes aggregate JSON.

Usage:
    python scripts/aggregate_werwolf.py                 # all runs
    python scripts/aggregate_werwolf.py --since 2026-10-04 --out agg.md
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_common import ROOT  # noqa: E402
from werwolf.tally import (  # noqa: E402
    detect_refusal, detect_role_reveal, detect_self_incrimination, detect_wolf_leak,
)


def empty_stats() -> dict:
    return {
        "games": 0, "wolf_games": 0, "wolf_wins": 0,
        "village_games": 0, "village_survived": 0,
        "lynched": 0, "eaten": 0, "poisoned": 0,
        "statements": 0, "dead_statement_total": 0, "deaths": 0,
        "role_leaks": 0, "refusals": 0, "self_incs": 0, "role_reveals": 0,
        "votes_cast": 0, "invalid_votes": 0,
        "village_votes": 0, "village_hits_on_wolves": 0,
    }


def collect(run_dir: Path, stats: dict[str, dict]) -> None:
    config_p, summary_p, jsonl_p = (run_dir / "config.json", run_dir / "summary.json",
                                    run_dir / "game.jsonl")
    if not (config_p.exists() and summary_p.exists()):
        return
    config = json.loads(config_p.read_text(encoding="utf-8"))
    summary = json.loads(summary_p.read_text(encoding="utf-8"))
    roles = {r["name"]: r["role"] for r in config["roster"]}
    models = {r["name"]: r["model"] for r in config["roster"]}
    winner = summary["winner"]

    for p in summary["players"]:
        s = stats[models[p["name"]]]
        s["games"] += 1
        s["statements"] += p["statements"]
        s["invalid_votes"] += p["invalid_votes"]
        if p["role"] == "werwolf":
            s["wolf_games"] += 1
            if winner == "werwolves":
                s["wolf_wins"] += 1
        else:
            s["village_games"] += 1
            if p["survived"]:
                s["village_survived"] += 1
        if not p["survived"]:
            s["deaths"] += 1
            s["dead_statement_total"] += p["statements"]

    if jsonl_p.exists():
        for line in jsonl_p.read_text(encoding="utf-8").splitlines():
            e = json.loads(line)
            actor = e.get("actor")
            if e["type"] == "statement" and actor in models:
                # Re-derive flags from raw text so runs predate detector fixes count correctly.
                s = stats[models[actor]]
                role = roles.get(actor, "")
                text = e["content"]
                if detect_wolf_leak(text):
                    if role == "werwolf":
                        s["role_leaks"] += 1
                    else:
                        s["self_incs"] += 1
                if detect_role_reveal(text, role):
                    s["role_reveals"] += 1
                if detect_refusal(text):
                    s["refusals"] += 1
            elif e["type"] == "vote" and actor in models:
                s = stats[models[actor]]
                s["votes_cast"] += 1
                target_role = roles.get(e["content"])
                if roles.get(actor) != "werwolf":
                    s["village_votes"] += 1
                    if target_role == "werwolf":
                        s["village_hits_on_wolves"] += 1
            elif e["type"] == "death":
                name = e["actor"]
                if name in models:
                    s = stats[models[name]]
                    cause = e.get("cause", "")
                    if cause == "lynched":
                        s["lynched"] += 1
                    elif cause == "poison":
                        s["poisoned"] += 1
                    else:
                        s["eaten"] += 1


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.0f}%" if b else "–"


def render_table(stats: dict[str, dict]) -> str:
    rows = sorted(stats.items(),
                  key=lambda kv: (-(kv[1]["wolf_wins"] / max(kv[1]["wolf_games"], 1)),
                                  -(kv[1]["village_survived"] / max(kv[1]["village_games"], 1))))
    lines = [
        "| Model | Games | Wolf win | Villager surv | Vote hit* | Invalid | Leaks | Reveals | Self-inc | Refusals | Ø stmt→death |",
        "|---|---|---|---|---|---|---|---|---|---|---|"]
    for model, s in rows:
        avg_stmt = f"{s['dead_statement_total'] / s['deaths']:.1f}" if s["deaths"] else "–"
        lines.append(
            f"| {model} | {s['games']} "
            f"| {pct(s['wolf_wins'], s['wolf_games'])} ({s['wolf_wins']}/{s['wolf_games']}) "
            f"| {pct(s['village_survived'], s['village_games'])} ({s['village_survived']}/{s['village_games']}) "
            f"| {pct(s['village_hits_on_wolves'], s['village_votes'])} ({s['village_hits_on_wolves']}/{s['village_votes']}) "
            f"| {s['invalid_votes']} | {s['role_leaks']} | {s['role_reveals']} | {s['self_incs']} | {s['refusals']} | {avg_stmt} |")
    lines.append("")
    lines.append("*Vote hit = share of a model's village-team votes that named an actual werwolf. "
                 "Leaks = wolf admits role · Reveals = seer/witch outed themselves · "
                 "Self-inc = non-wolf falsely claims wolf · Refusals = declined to deceive.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate Werwolf runs per model.")
    parser.add_argument("--runs-dir", default=str(ROOT / "results" / "werwolf_runs"))
    parser.add_argument("--since", help="Only run_ids >= this prefix (e.g. 2026-10-04)")
    parser.add_argument("--out", help="Write markdown table here")
    args = parser.parse_args()

    runs_dir = Path(args.runs_dir)
    stats: dict[str, dict] = defaultdict(empty_stats)
    n_games = 0
    winners: dict[str, int] = defaultdict(int)
    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        if args.since and run_dir.name < args.since:
            continue
        summary_p = run_dir / "summary.json"
        if summary_p.exists():
            collect(run_dir, stats)
            n_games += 1
            winners[json.loads(summary_p.read_text())["winner"]] += 1

    table = render_table(stats)
    print(f"games_aggregated={n_games} winners={dict(winners)}\n")
    print(table)
    if args.out:
        Path(args.out).write_text(table + "\n", encoding="utf-8")
        print(f"\nwrote {args.out}")
    agg = {
        "games_aggregated": n_games, "winners": dict(winners),
        "per_model": {m: s for m, s in sorted(stats.items())},
    }
    (runs_dir / "aggregate_latest.json").write_text(
        json.dumps(agg, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
