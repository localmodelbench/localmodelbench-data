# lmb-werwolf — local LLMs playing Werwolf (Mafia)

Companion data + harness for the Local Model Bench article
*"We made 8 local LLMs play Werwolf. The liars won."* (localmodelbench.com)

We ran **25 games** of the social-deduction game Werwolf with **local LLMs as players** on a
Mac mini M4 Pro (64 GB, Ollama). Eight seats: `qwen3.8:27b-mlx`, `lmb-runtime-phi4` (Phi-4) ×2,
`granite4.1:8b` ×2, `mistral:7b`, `llama3.1:8b`, `smollm2:135m`.

## Layout

```
scripts/
  werwolf/            # engine (state machine + info partitioning), player (Ollama client),
                      # prompts (role/night/day/vote templates), tally (JSON vote parsing + detectors)
  run_werwolf_game.py     # one game: --model X or --roster-file roster.json --seed N
  run_werwolf_batch.py    # N games, manifest output
  aggregate_werwolf.py    # per-model scoreboard from all run dirs
  bench_common.py         # tiny shim (paths + filename sanitizer)
results/werwolf_runs/
  <run_id>/config.json   # roster with roles (GM view), seed, params
  <run_id>/game.jsonl    # every event: announcements, statements, votes, deaths,
                         # private wolf channel (visibility: private:wolves), seer checks
  <run_id>/summary.json  # winner, days, per-player stats, event flags
  batch_*.json           # batch manifests
  aggregate_latest.json  # aggregated scoreboard
```

## Event types in game.jsonl

`setup`, `announcement`, `statement` (public speech), `wolf_talk` / `wolf_vote` /
`wolf_target` (private channel), `seer_check`, `witch_action`, `vote`, `invalid_vote`,
`death`, `role_leak`, `role_reveal`, `self_incrimination`, `moral_refusal`, `llm_error`.
Events carry `visibility` (`public`, `private:<name>`, `private:wolves`) — the engine
guarantees no player ever saw another seat's private context.

## Reproduce

```sh
pip install -r /dev/null   # stdlib only; needs Ollama running locally
ollama pull granite4.1:8b  # + the other roster models, or pass --model <one model>
python3 scripts/run_werwolf_game.py \
  --roster-file scripts/werwolf/roster_mixed_v1.json --seed 99
python3 scripts/aggregate_werwolf.py
```

Rules: 8 seats (2 Werwolves, 1 Seer, 1 Witch, 4 Villagers), 2 discussion rounds/day,
strict JSON ballots (1 retry, then abstention), ties decided by seeded RNG, max 8 days.
Models are stateless — the game master rebuilds each seat's allowed context per turn.

## Headline numbers (25 games)

| Model | Wolf wins | Village survival | Vote hit* | Bad ballots |
|---|---|---|---|---|
| lmb-runtime-phi4 | 5/6 (83%) | 20/36 (56%) | 29/68 (43%) | 0 |
| granite4.1:8b | 16/21 (76%) | 20/53 (38%) | 22/77 (29%) | 15 |
| qwen3.8:27b | 3/4 (75%) | 4/17 (24%) | 10/20 (50%) | 0 |
| mistral:7b | 4/6 (67%) | 9/15 (60%) | 9/30 (30%) | 1 |
| llama3.1:8b | 4/6 (67%) | 6/15 (40%) | 9/29 (31%) | 0 |
| smollm2:135m | 0/7 (0%) | 0/14 (0%) | 0/1 (0%) | 27 |

*Vote hit = share of non-wolf seats' day votes naming an actual wolf.
Sample sizes are small — treat as a starting signal, not a leaderboard.
