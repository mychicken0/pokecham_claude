# 09 — Stat / Damage / Type / Board Math Guide v29.40

This file owns numeric and mechanical math. Source policy lives in `02`; command syntax lives in `04`.

## 1. Stat formula

Pokémon Champions level 50 formula used by the verifier:

```text
HP = Base HP + 75 + HP investment
Non-HP = floor((Base + 20 + investment) * nature_modifier)
```

Displayed stats must come from `verify.py stat` or team render receipts. No stat receipt = no stat number or public stat adjective such as ถึก/บาง/เร็ว/ช้า, bulky/frail/fast/slow. Do not use mainline stat formulas, EV/IV language, or hand-computed stats in final prose.

## 2. Investment rules

Champions investment is not 252 EVs.

- Each stat investment: 0-32.
- Total investment: exactly 66/66.
- Public spread format must label stats: `HP 2 / Atk 32 / Def 0 / SpA 0 / SpD 0 / Spe 32`.
- Bare slash spreads are not public-safe unless the order is explicitly labeled.

## 3. Active form stat source

Active form must be resolved before stat, type, ability, damage, and public display.

Examples:

- Mega form uses Mega base stats and active battle ability.
- Aegislash stance uses active stance row.
- Palafin Hero-style claims fail closed unless the local active form row and trigger are present.

No active-form receipt = no active-form stat/type/ability claim.

## 4. Typechart multiplication

Use `verify.py typechart` for every type-effectiveness claim.

- Multiply across all defender types.
- Do not stop after the first type.
- 0x immunity overrides by multiplication.
- Public words such as immune/resist/super effective/neutral/weak/0x/0.5x/2x require a typechart receipt.

Locked examples:

```text
Ghost → Dark = 0.5x resisted
Ghost → Normal = 0x immune
Fire → Steel/Dragon = 1x neutral
Fighting → Steel/Dragon = 2x super_effective
Ground → Flying = 0x immune
```

## 5. Type passive properties

Typechart is not typepassive. Use `verify.py typepassive` for type-wide passive/status/weather/hazard properties.

Covered local passive families include:

- Grass vs Leech Seed / powder / spore.
- Fire burn immunity.
- Electric paralysis immunity.
- Ground vs Thunder Wave.
- Flying ungrounded hazard immunity.
- Rock/Ground/Steel sandstorm chip immunity.
- Rock SpD boost in sandstorm.
- Ice Defense boost in snow and hail chip immunity.
- Poison/Steel poison immunity with Corrosion exception.
- Grounded Poison clearing Toxic Spikes.
- Ghost trapping/cannot-escape immunity.
- Dark vs opposing Prankster-boosted Status moves.

No typepassive receipt = no passive/status/weather/hazard claim.

## 6. Weather and field stat modifiers

Weather/field stat changes must come from receipts, not memory.

Examples requiring receipts:

- Sandstorm Rock SpD modifier.
- Snow Ice Defense modifier.
- Weather speed abilities such as Sand Rush / Swift Swim / Chlorophyll / Slush Rush.
- Terrain or field rules such as Electric Terrain / Aurora Veil.

## 7. Damage receipt rules

Use `verify.py damage` for concrete damage claims. v29.40 damage receipts must expose `modifier_breakdown`; if STAB/type/weather/item/ability sources are hidden, the damage receipt is incomplete.

Public claims requiring damage/sequence receipts:

- OHKO / 2HKO.
- survival / guaranteed survival.
- damage ranges or percentages.
- Life Orb / weather / terrain / item damage modifiers.
- Stamina or staged-hit sequence claims.


### 7.1 Damage modifier strictness

`verify.py damage` may use local core STAB and typechart, but every modifier must be visible:

```text
stab: source LOCAL_DAMAGE_ENGINE_CORE_STAB
type: source verify.py typechart
weather/item/ability: applied only with explicit verified receipt; otherwise source says not applied
```

Do not infer these from memory inside damage prose: Life Orb, Choice Band/Specs, Adaptability, Supreme Overlord, Sun/Rain damage, Weather Ball type/power, Solar Beam charge skip, or Helping Hand.

Damage calc input provenance matters. A valid damage number from a `LOCAL_FALLBACK` spread is not a meta benchmark. Label it as local/experimental unless the spread source is `META_SPREAD_DIRECT`, `TOURNAMENT_LIST_DIRECT`, or `USER_PROVIDED`.

## 8. Speed and priority resolution

Priority bracket is resolved before Speed. Speed only sorts within the same bracket.

Use receipts for:

- Fake Out priority.
- Prankster status priority.
- Trick Room priority and speed reversal.
- Tailwind/weather speed benchmarks.
- Gale Wings and other priority modifiers.
- Choice Scarf or item speed claims.

## 9. Board interaction math

For 2v2/Doubles, do not analyze as 1v1. Board claims require boardscan/interaction/counterroute receipts.

Check:

- all four slots
- ally damage
- Protect/Wide Guard
- redirection
- spread moves
- type immunity
- ability immunity/blocking
- field/terrain/weather conditions
- active form
- speed/priority order

Earthquake and other ally-hitting spread moves need ally-safety matrix before public “safe/good partner” claims.


## 10. Item-spread and survival benchmark policy

Do not use bulk/survival language without a receipt. Public claims that a spread “รอด”, “ทน”, “รับได้”, “survives”, “lives”, or “tanks” require a damage or sequence receipt.

Focus Sash reasoning is checked by item-spread coherence:

- default value: Speed, damage, or utility timing;
- bulky Sash spread: requires meta spread evidence or damage benchmark;
- weather/field move interactions used as spread reasons require mechanic, interaction, boardscan, or typepassive receipts.

## 11. Semantic threat and item math

Risk and item explanations must start from a semantic threat profile, not from a single remembered weakness.

Use:

```bash
python3 scripts/verify.py threataudit <team.json>
python3 scripts/verify.py itemthreatfit <team.json>
```

`threataudit` checks all type multipliers, base stat profile, and board risks such as ally Earthquake. `itemthreatfit` checks whether a defensive item/berry matches the full threat profile.

Examples:

- Steel/Dragon is Fighting 2x and Ground 2x, not Fighting 4x.
- “ถึกสองด้าน” needs HP/Def/SpD support; high Def with low SpD is physical bulk, not mixed bulk.
- Chople vs Shuca must compare Fighting weakness, Ground weakness, and actual board risk.
- If `verify.py mechanic Stamina` or `verify.py mechanic "Electro Shot"` fails, use only the `08` description wording and do not add exact `+1`/sequence details.

## 12. Benchmark policy

Meta baseline is the default for actionable builds. Team-fit override requires a benchmark.

Speed override needs speed benchmark.
Bulk override needs damage/survival benchmark.
Item/move override needs mechanic/team-fit/source reason.

If no benchmark supports the override, keep the meta baseline or label the alternative as `LOCAL_FALLBACK` / `EXPERIMENTAL`.


## 13. Speed-mode planning

Tailwind/Trick Room advice must use actual Speed receipts, not vague labels. Compare raw Speed, Tailwind effective Speed, Trick Room ordering, and priority bracket.

- Tailwind helps the active side when its intended attackers need to win the speed race.
- Trick Room helps the active side only when its intended attackers are slower than the relevant opponents.
- Trick Room can help the opponent if their active attackers are slower than yours.
- A team with Tailwind + Trick Room needs separate mode explanations and rejected/conditional lines.

No speedplan receipt = no public speed-mode recommendation.

