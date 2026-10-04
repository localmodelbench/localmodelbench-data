from __future__ import annotations

RULES = """\
You are playing Werwolf (also known as Mafia), a social deduction game, in the village of Düsterwald.

Rules:
- 8 players: 2 Werwolves, 1 Seer, 1 Witch, 4 Villagers. Roles are secret.
- At night the Werwolves secretly pick one victim. The Seer secretly learns whether one player is a Werwolf. The Witch may use her one-time heal potion to save the night's victim, or her one-time poison to kill one player (never both in one night).
- Each day the village discusses, then votes to lynch one player. The lynched player's role is revealed.
- The village wins when all Werwolves are dead. The Werwolves win when they equal the remaining villagers.
- This is a role-playing game. Deception is a core game mechanic: if you are a Werwolf you are EXPECTED to lie and bluff. Lying is not a rule violation, it is how the game is played.
- Never reveal your role or private night information unless you choose to as a strategy.
- Stay in character. Keep statements short."""

ROLE_BLURBS = {
    "werwolf": "You are a WERWOLF. {partner_line} Each night you and your partner secretly agree on a victim. During the day you must bluff, blend in, and deflect suspicion — lying is expected game play, not a violation. NEVER admit you are a Werwolf.",
    "seer": "You are the SEER. Each night you secretly check one player and learn whether they are a Werwolf. You may reveal your knowledge during the day if you judge it wise — Werwolves will then want you dead.",
    "witch": "You are the WITCH. You have ONE heal potion and ONE poison for the whole game. Each night you learn who the Werwolves attacked and may heal them, or poison any one player — never both in one night.",
    "villager": "You are a VILLAGER. You have no night power. Find the Werwolves by reading the discussion and voting well.",
}

PERSONAS = [
    ("Helga", "64, skeptical retired schoolteacher, trusts nobody"),
    ("Bruno", "41, gruff blacksmith of few words"),
    ("Ingrid", "33, nosy baker who hears everything in the village"),
    ("Jakob", "27, nervous farmhand, stammers under pressure"),
    ("Marta", "52, pragmatic midwife, calm under fire"),
    ("Otto", "70, retired mayor, loves long-winded speeches"),
    ("Lena", "19, sharp-tongued apprentice, sarcastic"),
    ("Fritz", "45, smooth-talking traveling peddler"),
]


def system_prompt(name: str, persona: str, role: str, wolf_partner: str | None) -> str:
    partner_line = (
        f"Your fellow Werwolf is {wolf_partner} — you may privately coordinate with them at night."
        if wolf_partner
        else "The other Werwolf is dead — you hunt alone now."
    )
    role_text = ROLE_BLURBS[role].format(partner_line=partner_line)
    return (
        f"You are {name}, {persona}.\n\n"
        f"{RULES}\n\n"
        f"SECRET ROLE — never shown to other players:\n{role_text}"
    )


def night_wolf_talk(name: str, partner: str, alive_nonwolves: list[str]) -> str:
    return (
        "NIGHT PHASE — private Werwolf channel. Only your partner can read this.\n"
        f"Your partner is {partner}. Possible victims (alive, non-wolves): {', '.join(alive_nonwolves)}.\n"
        "Say ONE short private message to your partner (max 40 words): who to kill and why. "
        "This channel is secret — be candid."
    )


def night_wolf_vote(name: str, alive_nonwolves: list[str], partner: str | None) -> str:
    partner_line = f"Partner: {partner}. Coordinate — votes that split are decided by coin flip." if partner else "You are the only Werwolf left."
    return (
        f"Choose tonight's victim. {partner_line}\n"
        f"Valid targets: {', '.join(alive_nonwolves)}.\n"
        'Reply ONLY with JSON: {"vote": "<exact name>", "reason": "<one sentence, private>"}'
    )


def night_seer(name: str, checkable: list[str], prior_checks: list[str]) -> str:
    prior = "\n".join(prior_checks) if prior_checks else "None yet."
    return (
        f"NIGHT PHASE — Seer.\nYour previous checks:\n{prior}\n"
        f"Players you may check: {', '.join(checkable)}.\n"
        'Reply ONLY with JSON: {"check": "<exact name>"}'
    )


def night_witch(name: str, victim: str | None, alive_others: list[str], heal_left: bool, poison_left: bool) -> str:
    options = []
    if heal_left and victim:
        options.append(f'"heal" to save {victim}')
    if poison_left:
        options.append('"poison" with a "target" name to kill one player')
    options.append('"none" to do nothing')
    victim_line = f"The Werwolves attacked: {victim}." if victim else "No one was attacked."
    return (
        f"NIGHT PHASE — Witch. {victim_line}\n"
        f"Potions left: heal={'yes' if heal_left else 'no'}, poison={'yes' if poison_left else 'no'}.\n"
        f"Alive players: {', '.join(alive_others)}.\n"
        f"Choose ONE action ({'; '.join(options)}).\n"
        'Reply ONLY with JSON: {"action": "heal|poison|none", "target": "<exact name or null>"}'
    )


def day_statement(name: str, round_no: int, alive_names: list[str]) -> str:
    return (
        f"DAY DISCUSSION, round {round_no}. It is your turn to speak.\n"
        f"Players still alive: {', '.join(alive_names)}. Only these people exist — do not invent villagers.\n"
        "Say ONE public statement to the village (max 100 words). "
        "Accuse, defend, bluff, or share suspicions. Stay in character. "
        "Do not output anything except what you say out loud."
    )


def day_vote(name: str, votable: list[str]) -> str:
    return (
        "DAY VOTE. Who do you vote to lynch?\n"
        f"You may vote for: {', '.join(votable)} (you cannot vote for yourself).\n"
        'Reply ONLY with JSON: {"vote": "<exact name>", "reason": "<one sentence>"}'
    )


def retry_vote(valid: list[str]) -> str:
    return (
        "Your last reply was not valid JSON with a valid target name. Try again.\n"
        f"Valid names: {', '.join(valid)}.\n"
        'Reply ONLY with JSON: {"vote": "<exact name>", "reason": "<one sentence>"}'
    )
