# 02 — Live / Player Meta Search Guide v29.38

This file owns live/player/meta source policy. Legality and mechanics remain local/verifier responsibilities.

## 1. When live meta search is mandatory

Live/player baseline search is mandatory for every actionable answer that recommends, ranks, edits, counters, builds, replaces, or explains a team/set/move/item/ability/nature/spread/lead/risk/matchup plan.

Do not invent the first build. Start from what players actually use, then local-verify and team-fit it.

Pure legality/mechanic/math/debug questions do not require live search unless they become actionable advice.

## 2. Approved source families

Use sources specific to Pokémon Champions / Champions Ranked / Champion mode / 2v2 / Doubles where possible:

- Pikalytics Pokémon Champions pages.
- Pokémon-Zone Champions pages.
- PokéBase Pokémon Champions pages.
- Champions Lab.
- OP.GG Pokémon Champions pages.
- Limitless / Play Limitless / tournament teamlists.
- RK9 or official tournament pages when relevant.
- Official Pokémon / Pokémon Champions pages for official rule or game information.

Use diverse sources when possible. Prefer primary usage/teamlist evidence over generic guide pages.

## 3. Blocked or contaminated sources

Do not use as proof:

- BlueStacks or emulator/app guide pages.
- Generic SEO tier lists not specific to Champions competitive play.
- Mainline VGC, Smogon, Showdown, Scarlet/Violet, or old-generation pages unless the user explicitly asks for comparison; even then, label as non-Champions context.

If blocked sources appear in search, ignore them and do not cite them as checked sources.

## 4. Search workflow

For actionable advice:

1. Search approved sources for the exact Pokémon/form/core/team/matchup.
2. Extract candidate Pokémon, moves, items, abilities, natures, spreads, leads, counters, and usage numbers.
3. Quarantine every candidate.
4. Pass candidates to local verification.
5. Keep the meta baseline visible until final decision.
6. If team-fit changes the baseline, show the diff and benchmark reason.

## 5. Player/meta baseline extraction

Extract only what the source supports:

```json
{
  "pokemon": "...",
  "form": "...",
  "ability": "...",
  "item": "...",
  "moves": ["..."],
  "nature": "...",
  "spread": {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
  "usage": "...",
  "source_url_or_name": "...",
  "source_label": "META_DIRECT"
}
```

Do not fill missing move/item/spread slots from memory. Missing data remains missing until verified by another approved source or becomes `LOCAL_FALLBACK` after search.

## 6. Usage-ranked moves/items/spreads

When usage data exists, treat the top usage option as the baseline, not the final truth.

- Use top moves/items/spreads as the first candidate set.
- Keep usage numbers in the receipt/summary when relevant.
- Do not replace a high-usage move/spread with a local-only idea unless benchmark or team-fit proves the override.

Example policy:

```text
Meta baseline: Dragon Pulse — META_DIRECT, 73.5% usage.
Local-only alternative: Thunder Wave — legal, but not baseline. Use only if team-fit/benchmark justifies it.
```

## 7. Tournament/teamlist evidence

Tournament/teamlist evidence can override aggregate usage when it is more relevant to the user's requested core, format, or metagame.

Label it as `TOURNAMENT_LIST_DIRECT` and still local-verify every entity.

## 8. Missing data behavior

If no approved source provides a move/item/spread after search:

1. Say the baseline slot is missing.
2. Use `LOCAL_FALLBACK` only after local verification.
3. Do not call it meta.
4. Avoid high-confidence language such as “ดีที่สุด”, “แน่”, “standard” unless supported.

## 9. Passing candidates to the verifier

After extraction, every public entity must pass local verification:

- Pokémon/form: `01_ranked_champions_pokemon_core.csv`.
- Move legality: exact Pokémon/form row + `05-07` move files.
- Ability: Pokémon/form allowed ability.
- Item: `08_global_moves_abilities_items.csv` item row.
- Spread: 0-32 per stat, exactly 66 total.
- Active form: resolved before stats, typing, ability, and damage.

Live meta creates candidates; local verification decides if they may appear in final output. Feed the extracted baseline into the decision trace before final play/lead recommendations.
