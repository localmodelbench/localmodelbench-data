from __future__ import annotations

import json
import random
import time
from pathlib import Path

from . import prompts, tally
from .player import LLMClient, Player

PUBLIC_CONTEXT_CHARS = 14000  # ~3.5k tokens rough cap


class Game:
    def __init__(self, players: list[Player], client: LLMClient, out_dir: Path,
                 seed: int = 0, max_days: int = 8, temperature: float = 0.7,
                 discussion_rounds: int = 2, verbose: bool = True):
        self.players = players
        self.client = client
        self.out_dir = out_dir
        self.rng = random.Random(seed)
        self.seed = seed
        self.max_days = max_days
        self.temperature = temperature
        self.discussion_rounds = discussion_rounds
        self.verbose = verbose

        self.day = 0
        self.seq = 0
        self.public_log: list[str] = []          # lines every player may see
        self.vote_history: list[str] = []        # public vote records
        self.events: list[dict] = []
        self.heal_left = True
        self.poison_left = True
        self.winner: str | None = None
        self._jsonl = open(out_dir / "game.jsonl", "w", encoding="utf-8")

    # ---------- logging ----------

    def log(self, event_type: str, actor: str | None, content: str,
            visibility: str = "public", **extra) -> dict:
        self.seq += 1
        event = {
            "seq": self.seq, "day": self.day, "type": event_type,
            "actor": actor, "visibility": visibility, "content": content,
            "ts": round(time.time(), 2), **extra,
        }
        self.events.append(event)
        self._jsonl.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._jsonl.flush()
        return event

    def announce(self, text: str) -> None:
        self.log("announcement", "GM", text)
        self.public_log.append(f"[Day {self.day}] GM: {text}")
        if self.verbose:
            print(f"\n\033[1m— {text}\033[0m")

    def public_statement(self, player: Player, text: str) -> None:
        line = f"[Day {self.day}] {player.name}: {text}"
        self.public_log.append(line)
        player.private_memory.append(f"You said publicly: {text}")
        if self.verbose:
            print(f"  {player.name}: {text}")

    # ---------- context ----------

    def public_context(self) -> str:
        text = "\n".join(self.public_log)
        if len(text) <= PUBLIC_CONTEXT_CHARS:
            return text
        # keep headline events (deaths/votes) + most recent discussion tail
        headlines = [l for l in self.public_log if l.startswith("[Day") and "GM:" in l]
        tail = text[-PUBLIC_CONTEXT_CHARS // 2 :]
        joined = "\n".join(headlines) + "\n… (older discussion omitted) …\n" + tail
        return joined[-PUBLIC_CONTEXT_CHARS:]

    def private_context(self, player: Player) -> str:
        if not player.private_memory:
            return "(none yet)"
        mem = player.private_memory[-30:]
        return "\n".join(f"- {m}" for m in mem)

    def ask(self, player: Player, instruction: str, max_tokens: int = 400) -> dict:
        """One LLM turn for a player: system(persona+role) + public ctx + private ctx + instruction."""
        wolves = [p for p in self.players if p.is_wolf]
        partner = next((w.name for w in wolves if w is not player and w.alive), None) if player.is_wolf else None
        user = (
            f"PUBLIC TRANSCRIPT SO FAR:\n{self.public_context() or '(game just started)'}\n\n"
            f"YOUR PRIVATE MEMORY (only you see this):\n{self.private_context(player)}\n\n"
            f"---\n{instruction}"
        )
        messages = [
            {"role": "system", "content": prompts.system_prompt(player.name, player.persona, player.role, partner)},
            {"role": "user", "content": user},
        ]
        try:
            return self.client.chat(player.model, messages, temperature=self.temperature,
                                  max_tokens=max_tokens)
        except Exception as exc:
            self.log("llm_error", player.name, str(exc), visibility=f"private:{player.name}")
            return {"content": "", "thinking": "", "raw": {"error": str(exc)}}

    # ---------- helpers ----------

    def alive(self) -> list[Player]:
        return [p for p in self.players if p.alive]

    def alive_names(self, exclude: Player | None = None) -> list[str]:
        return [p.name for p in self.alive() if p is not exclude]

    def find(self, name: str) -> Player | None:
        return next((p for p in self.players if p.name == name), None)

    def kill(self, player: Player, cause: str) -> None:
        player.alive = False
        self.log("death", player.name, f"{player.name} died ({cause}). Role was: {player.role}.",
                 role=player.role, cause=cause)

    def check_win(self) -> str | None:
        wolves = [p for p in self.alive() if p.is_wolf]
        villagers = [p for p in self.alive() if not p.is_wolf]
        if not wolves:
            return "village"
        if len(wolves) >= len(villagers):
            return "werwolves"
        return None

    # ---------- night ----------

    def wolf_names(self) -> list[str]:
        return [p.name for p in self.players if p.is_wolf]

    def night_phase(self) -> list[tuple[Player, str]]:
        """Returns [(player, cause)] who die during the night."""
        deaths: list[tuple[Player, str]] = []
        wolves = [p for p in self.alive() if p.is_wolf]
        targets = [p.name for p in self.alive() if not p.is_wolf]
        victim_name: str | None = None

        # 1. wolves: private channel talk (1 round) then vote
        if len(wolves) == 2:
            for w in wolves:
                partner = next(x for x in wolves if x is not w)
                res = self.ask(w, prompts.night_wolf_talk(w.name, partner.name, targets), max_tokens=150)
                msg, truncated = tally.cap_words(res["content"], 60)
                self.log("wolf_talk", w.name, msg, visibility="private:wolves",
                         thinking=res.get("thinking") or "", truncated=truncated)
                partner.private_memory.append(f"Wolf channel, night {self.day}, {w.name}: {msg}")
                w.private_memory.append(f"Wolf channel, night {self.day}, you said: {msg}")
                if self.verbose:
                    print(f"  [wolves] {w.name}: {msg}")

        votes: dict[str, list[str]] = {}
        for w in wolves:
            partner = next((x for x in wolves if x is not w), None)
            res = self.ask(w, prompts.night_wolf_vote(w.name, targets, partner.name if partner else None),
                           max_tokens=120)
            name, reason, err = tally.parse_vote(res["content"], targets)
            if name is None:
                # one retry
                res = self.ask(w, prompts.retry_vote(targets), max_tokens=120)
                name, reason, err2 = tally.parse_vote(res["content"], targets)
                if name is None:
                    self.log("invalid_wolf_vote", w.name, res["content"],
                             visibility="private:wolves", error=err2)
                    name = self.rng.choice(targets)
            votes.setdefault(name, []).append(w.name)
            self.log("wolf_vote", w.name, name, visibility="private:wolves", reason=reason)

        if len(votes) == 1:
            victim_name = next(iter(votes))
        elif votes:
            tied = sorted(votes, key=lambda n: -len(votes[n]))
            top = [n for n in tied if len(votes[n]) == len(votes[tied[0]])]
            victim_name = self.rng.choice(top)
        self.log("wolf_target", "GM", victim_name or "", visibility="private:wolves")

        # 2. seer
        seer = next((p for p in self.alive() if p.role == "seer"), None)
        if seer:
            prior = [m for m in seer.private_memory if m.startswith("Seer check:")]
            res = self.ask(seer, prompts.night_seer(seer.name, self.alive_names(exclude=seer), prior),
                           max_tokens=120)
            name, err = tally.parse_named_field(res["content"], "check", self.alive_names(exclude=seer))
            if name is None:
                name = self.rng.choice(self.alive_names(exclude=seer))
                self.log("invalid_seer_check", seer.name, res["content"],
                         visibility=f"private:{seer.name}", error=err)
            target = self.find(name)
            is_wolf = bool(target and target.is_wolf)
            result = f"Seer check: {name} is {'A WERWOLF' if is_wolf else 'not a werwolf'}."
            seer.private_memory.append(result)
            self.log("seer_check", seer.name, result, visibility=f"private:{seer.name}",
                     target=name, is_wolf=is_wolf)
            if self.verbose:
                print(f"  [seer] {seer.name} checks {name} -> {'WOLF' if is_wolf else 'clean'}")

        # 3. witch
        witch = next((p for p in self.alive() if p.role == "witch"), None)
        healed = False
        poisoned: Player | None = None
        if witch and (self.heal_left or self.poison_left):
            others = self.alive_names(exclude=witch)
            res = self.ask(
                witch,
                prompts.night_witch(witch.name, victim_name, others, self.heal_left, self.poison_left),
                max_tokens=120,
            )
            action, target_name, err = tally.parse_witch_action(
                res["content"], victim_name, others, self.heal_left, self.poison_left)
            if err:
                self.log("invalid_witch_action", witch.name, res["content"],
                         visibility=f"private:{witch.name}", error=err)
            if action == "heal" and victim_name:
                self.heal_left = False
                healed = True
                witch.private_memory.append(f"Night {self.day}: you healed {victim_name}.")
            elif action == "poison" and target_name:
                self.poison_left = False
                poisoned = self.find(target_name)
                witch.private_memory.append(f"Night {self.day}: you poisoned {target_name}.")
            self.log("witch_action", witch.name, f"{action} {target_name or ''}".strip(),
                     visibility=f"private:{witch.name}", action=action, target=target_name)
            if self.verbose:
                print(f"  [witch] {witch.name}: {action} {target_name or ''}")

        if victim_name and not healed:
            v = self.find(victim_name)
            if v:
                deaths.append((v, "werwolf"))
        if poisoned and poisoned.alive and poisoned not in [d for d, _ in deaths]:
            deaths.append((poisoned, "poison"))
        return deaths

    # ---------- day ----------

    def day_phase(self) -> None:
        for round_no in range(1, self.discussion_rounds + 1):
            if self.verbose:
                print(f"\n  Discussion round {round_no}:")
            for p in self.alive():
                res = self.ask(p, prompts.day_statement(p.name, round_no, self.alive_names()),
                               max_tokens=220)
                text, truncated = tally.cap_words(res["content"], 120)
                flags = {}
                if p.is_wolf and tally.detect_wolf_leak(text):
                    flags["role_leak"] = True
                    self.log("role_leak", p.name, text, role=p.role)
                elif not p.is_wolf and tally.detect_self_incrimination(text):
                    flags["self_incrimination"] = True
                    self.log("self_incrimination", p.name, text, role=p.role,
                             visibility="public_meta")
                if tally.detect_role_reveal(text, p.role):
                    flags["role_reveal"] = True
                    self.log("role_reveal", p.name, text, role=p.role,
                             visibility="public_meta")
                if tally.detect_refusal(text):
                    flags["refusal"] = True
                    self.log("moral_refusal", p.name, text, visibility="public_meta")
                self.log("statement", p.name, text, thinking=res.get("thinking") or "",
                         truncated=truncated, **flags)
                self.public_statement(p, text)

        # vote
        vote_lines = []
        counts: dict[str, int] = {}
        for p in self.alive():
            valid = self.alive_names(exclude=p)
            res = self.ask(p, prompts.day_vote(p.name, valid), max_tokens=120)
            name, reason, err = tally.parse_vote(res["content"], valid)
            retried = False
            if name is None:
                retried = True
                res = self.ask(p, prompts.retry_vote(valid), max_tokens=120)
                name, reason, err = tally.parse_vote(res["content"], valid)
            if name is None:
                self.log("invalid_vote", p.name, res["content"], error=err, retried=retried)
                vote_lines.append(f"{p.name}: (abstain, invalid ballot)")
                continue
            counts[name] = counts.get(name, 0) + 1
            vote_lines.append(f"{p.name} -> {name}")
            self.log("vote", p.name, name, reason=reason, retried=retried)
        self.vote_history.append(f"Day {self.day} votes: " + "; ".join(vote_lines))
        self.public_log.append(self.vote_history[-1])
        if self.verbose:
            print(f"\n  Votes: {'; '.join(vote_lines)}")

        if not counts:
            self.announce("No valid votes — nobody is lynched today.")
            return
        top = max(counts.values())
        tied = [n for n, c in counts.items() if c == top]
        lynched_name = self.rng.choice(tied)
        if len(tied) > 1:
            self.announce(f"Tie between {', '.join(tied)} — the village flips a coin: {lynched_name}.")
        lynched = self.find(lynched_name)
        if lynched:
            self.kill(lynched, "lynched")
            self.announce(f"{lynched.name} is lynched. {lynched.name} was the {lynched.role.upper()}.")

    # ---------- main loop ----------

    def run(self) -> dict:
        roster = ", ".join(f"{p.name} ({p.model})" for p in self.players)
        self.log("setup", "GM", f"Game starts. Players: {roster}",
                 seed=self.seed,
                 roles={p.name: p.role for p in self.players})
        self.announce(
            "Night falls over Düsterwald. 8 villagers, 2 of them Werwolves. "
            "Everyone goes to sleep…")

        while self.day < self.max_days:
            self.day += 1
            if self.verbose:
                print(f"\n{'='*60}\nNIGHT {self.day}\n{'='*60}")
            night_deaths = self.night_phase()

            if self.verbose:
                print(f"\n{'='*60}\nDAY {self.day}\n{'='*60}")
            for p, cause in night_deaths:
                self.kill(p, cause)
            if night_deaths:
                names = ", ".join(f"{p.name} (the {p.role})" for p, _ in night_deaths)
                self.announce(f"Morning of day {self.day}. Dead in the night: {names}. "
                              f"{len(self.alive())} players remain.")
            else:
                self.announce(f"Morning of day {self.day}. Nobody died in the night. "
                              f"{len(self.alive())} players remain.")

            winner = self.check_win()
            if winner:
                break

            self.day_phase()
            winner = self.check_win()
            if winner:
                break

        if not winner:
            winner = "incomplete"
            self.announce("Game aborted: day limit reached.")
        else:
            self.announce(f"GAME OVER — the {winner.upper()} win!")

        summary = self.build_summary(winner)
        (self.out_dir / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        return summary

    def build_summary(self, winner: str) -> dict:
        role_leaks = [e for e in self.events if e["type"] == "role_leak"]
        invalid_votes = [e for e in self.events if e["type"] == "invalid_vote"]
        refusals = [e for e in self.events if e["type"] == "moral_refusal"]
        self_incs = [e for e in self.events if e["type"] == "self_incrimination"]
        role_reveals = [e for e in self.events if e["type"] == "role_reveal"]
        statements = {}
        for e in self.events:
            if e["type"] == "statement" and e["actor"]:
                statements[e["actor"]] = statements.get(e["actor"], 0) + 1
        per_player = []
        for p in self.players:
            per_player.append({
                "name": p.name, "model": p.model, "role": p.role,
                "survived": p.alive,
                "statements": statements.get(p.name, 0),
                "role_leaks": sum(1 for e in role_leaks if e["actor"] == p.name),
                "invalid_votes": sum(1 for e in invalid_votes if e["actor"] == p.name),
                "refusals": sum(1 for e in refusals if e["actor"] == p.name),
                "self_incs": sum(1 for e in self_incs if e["actor"] == p.name),
                "role_reveals": sum(1 for e in role_reveals if e["actor"] == p.name),
            })
        return {
            "winner": winner, "days": self.day, "seed": self.seed,
            "events": len(self.events),
            "role_leaks": len(role_leaks),
            "invalid_votes": len(invalid_votes),
            "moral_refusals": len(refusals),
            "self_incriminations": len(self_incs),
            "role_reveals": len(role_reveals),
            "players": per_player,
            "roles": {p.name: p.role for p in self.players},
        }
