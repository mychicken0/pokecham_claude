# 04 — Verification Harness Spec v29.46

This file owns `scripts/verify.py` commands, receipts, lint/selfaudit, and fail/warning code groups.


## v29.43 verifier package layout

Public CLI remains stable:

```bash
python3 scripts/verify.py <command> ...
```

`verify.py` is now a facade. Implementation seams live under `scripts/pokecham_verify/`:

```text
cli.py                  command router
legacy.py               v29.42-compatible engine bridge
type_matrix.py          incoming/outgoing direction-explicit type matrix receipts
switch_matrix.py        switch safety matrix receipts
regression.py           all-regression-tests
ids.py/data_loader.py/... thin extraction seams for future module moves
```

The facade is intentional: external skill docs and user workflows must not call multiple scripts directly.

## Direction-explicit matrix commands

```bash
python3 scripts/verify.py type-matrix <team.json> [targets.json] [--mode incoming-defense|outgoing-attack]
python3 scripts/verify.py incoming-defense-matrix <team.json>
python3 scripts/verify.py outgoing-attack-matrix <our_team.json> <enemy_targets.json>
python3 scripts/verify.py switch-safety-matrix <board.json>
```

Purpose: build receipt-backed type tables without attacker/defender direction ambiguity.

- `INCOMING_DEFENSE_MATRIX`: Direction `ENEMY MOVE TYPE → OUR DEFENDER`; cells must be public-written as `x taken`.
- `OUTGOING_ATTACK_MATRIX`: Direction `OUR MOVE → ENEMY DEFENDER`; cells must be public-written as `x dealt`.
- `SWITCH_SAFETY_MATRIX`: Direction `ENEMY LIKELY MOVE → OUR SWITCH-IN`; cells must be public-written as `x taken`.

Public-use rule: switch/swap/pivot advice requires `switch-safety-matrix` or `incoming-defense-matrix`; offensive coverage advice requires `outgoing-attack-matrix` or damage receipt.

## Regression command

```bash
python3 scripts/verify.py all-regression-tests
```

Run before packaging verifier changes. It includes mechanic data lint/coverage, typechart traps including `Ground → Sinistcha = 0.5x resisted` and `Fire → Kingambit = 2x super_effective`, typepassive/mechanic tests, and v29.44 switch-matrix lint gates.

## 1. Receipt principle

No receipt = no public claim. A receipt is a JSON result from `verify.py` or an explicitly captured approved live/player source baseline.

Entity verification is not mechanic verification. A Pokémon/move/ability/item can exist locally while its interaction remains unverified.

## 2. Core entity commands

```bash
python3 scripts/verify.py item <name_or_id>
python3 scripts/verify.py ability <pokemon_name_or_id> <ability_name>
python3 scripts/verify.py move <pokemon_name_or_id> <move_name>
python3 scripts/verify.py set <set.json>
python3 scripts/verify.py team <team.json>
python3 scripts/verify.py strict_mb <name_or_id>
python3 scripts/verify.py active-form <slot_or_scenario_json>
```

Core local files:

- Pokémon/form: `data/01_ranked_champions_pokemon_core.csv`.
- Moves: `data/05_pokemon_moves_part1.csv`, `06`, `07`.
- Global moves/abilities/items/mechanics: `data/08_global_moves_abilities_items.csv`.
- Type passive/status/weather/hazard rules: `data/09_type_passive_properties.csv`.

## 3. Team construction commands

```bash
python3 scripts/verify.py team <team.json>
python3 scripts/verify.py teamfit <team.json>
python3 scripts/verify.py spreadfit <team.json> [meta_spreads.json]
python3 scripts/verify.py itemspread <team.json>
python3 scripts/verify.py speedplan <team.json>
python3 scripts/verify.py leadplan <team.json>
python3 scripts/verify.py threataudit <team.json>
python3 scripts/verify.py itemthreatfit <team.json>
python3 scripts/verify.py threatfit <team.json> [meta_threats.json]
python3 scripts/verify.py receipt-strict <answer.md> <receipt.json>
```

Required for final team/set answers:

- Pokémon/form pass.
- Active form resolution pass.
- Ability pass on active form where applicable.
- Item exists and item clause pass.
- Moves pass on exact Pokémon/form.
- Spread total exactly 66/66 and each stat 0-32.
- Provenance labels present.
- Team-fit, spreadfit, itemspread, threataudit, and itemthreatfit warnings addressed or surfaced.

## 4. Meta baseline hardgate commands

For actionable advice, a per-slot meta/player baseline gate is required before final item/move/spread/nature/ability recommendation.

```bash
python3 scripts/verify.py meta-baseline-lint meta_baseline.json
python3 scripts/verify.py meta-baseline-gate team.json meta_baseline.json [--fields item,moves,spread,nature,ability]
python3 scripts/verify.py recommendation-provenance-lint answer.md receipt.json
```

Eligible final evidence labels:

- `META_DIRECT` / `META_SPREAD_DIRECT` / `TOURNAMENT_LIST_DIRECT` / `USER_REQUESTED` — direct source/user evidence for the exact slot.
- `LOCAL_FALLBACK_AFTER_SEARCH` — only after a matching approved `search_attempts[]` receipt with `no_results` or `unavailable`.
- `LOCAL_BENCHMARK_OVERRIDE` — only with `baseline_value`, `final_value`, and explicit diff/benchmark receipt summary.

Blocked as final evidence: `LOCAL_FALLBACK`, `LOCAL_TEAM_FIT`, `ITEM_CLAUSE_REPAIR`, `ITEMTHREATFIT`, `DAMAGE_BENCHMARK`, `SPEED_MODE_FIT`, `LOCAL_GUESS`, and `EXPERIMENTAL`. These may appear only as intermediate audit labels.

Minimal receipt shape:

```json
{
  "search_attempts": [
    {"pokemon":"Dragonite","field":"item","source_family":"Pikalytics","query":"...","result_status":"found"}
  ],
  "slot_baselines": [
    {"pokemon":"Dragonite","field":"item","value":"White Herb","baseline_status":"META_DIRECT","source_family":"Pikalytics"}
  ],
  "overrides": [
    {"pokemon":"Dragonite","field":"item","baseline_value":"White Herb","final_value":"Wacan Berry","baseline_status":"LOCAL_BENCHMARK_OVERRIDE","diff":"..."}
  ]
}
```

Fail/warn group:

```text
FAIL_ACTIONABLE_ITEM_RECOMMENDATION_WITHOUT_META_BASELINE
FAIL_META_DIRECT_WITHOUT_SOURCE
FAIL_ITEMTHREATFIT_USED_AS_META_BASELINE
FAIL_LOCAL_FALLBACK_WITHOUT_SEARCH_ATTEMPT
FAIL_META_BASELINE_SLOT_MISSING
```

## 5. Item-spread coherence receipts

Use `itemspread` or the team gate `item_spread_coherence` before final spread reasoning. This gate checks whether item, spread, and written reason agree.

Key fail/warn codes:

```text
FAIL_SASH_BULK_WITHOUT_BENCHMARK
FAIL_SURVIVAL_REASON_WITHOUT_DAMAGE_RECEIPT
FAIL_SURVIVAL_CLAIM_WITHOUT_DAMAGE_RECEIPT
FAIL_ITEM_SPREAD_REASON_CONFLICT
FAIL_WEATHER_MECHANIC_REASON_WITHOUT_RECEIPT
WARN_SASH_ACTION_VALUE_WEAKLY_JUSTIFIED
WARN_USER_REQUESTED_SASH_BULK_NO_BENCHMARK
```

A Focus Sash set should default to action value (Speed, damage, or utility timing). Bulky Focus Sash spreads need meta or damage-benchmark receipts.

## 6. Decision trace / speed and lead commands

```bash
python3 scripts/verify.py speedplan <team.json>
python3 scripts/verify.py leadplan <team.json>
```

Use `speedplan` before public Tailwind/Trick Room advice. It returns Speed receipts, Tailwind beneficiaries, Trick Room beneficiaries, slots hurt by Trick Room, and warnings such as `WARN_TRICK_ROOM_MAY_HELP_OPPONENT`.

Use `leadplan` before public lead advice. It returns candidate leads with short Turn 1–2 simulations and risks.

Fail/warn group:

```text
FAIL_SPEED_MODE_CLAIM_WITHOUT_SPEEDPLAN_RECEIPT
FAIL_TRICK_ROOM_RECOMMENDATION_WITHOUT_BENEFICIARY_CHECK
FAIL_LEAD_PLAN_WITHOUT_TURN_SIMULATION
WARN_DUAL_SPEED_MODE_CONFLICT
WARN_TRICK_ROOM_MAY_HELP_OPPONENT
WARN_TRICK_ROOM_BACKUP_NOT_MAIN_MODE
WARN_FAST_MON_HURT_BY_TRICK_ROOM
```

Do not call a team “dual mode” or recommend “TR into slow/bulky teams” unless speedplan supports it.

## 7. Semantic threat audit commands

```bash
python3 scripts/verify.py threataudit <team.json>
python3 scripts/verify.py itemthreatfit <team.json>
```

Use `threataudit` before risk, weakness, stat-adjective, or defensive item prose. It returns all weaknesses/resists/immunities, base stat profile, and board risks such as ally Earthquake.

Use `itemthreatfit` before explaining resist berries or defensive items. It compares item type against the full weakness profile and board risks.

Fail/warn group:

```text
FAIL_STAT_ADJECTIVE_WITHOUT_STAT_RECEIPT
FAIL_BULK_CLAIM_CONFLICTS_BASE_STATS
FAIL_MECHANIC_STAGE_CLAIM_WITHOUT_RECEIPT
FAIL_MOVE_SEQUENCE_CLAIM_WITHOUT_MECHANIC_RECEIPT
FAIL_08_DESCRIPTION_OVERINTERPRETED
FAIL_RISK_SECTION_WITHOUT_THREAT_AUDIT
FAIL_ITEM_REASON_WITHOUT_ITEMTHREATFIT_RECEIPT
FAIL_ITEM_THREAT_PROFILE_MISSING
FAIL_ITEM_REASON_IGNORES_HIGHER_BOARD_RISK
WARN_RESIST_BERRY_SELECTED_FROM_SINGLE_WEAKNESS
WARN_ITEM_MISALIGNED_WITH_BOARD_THREAT
```

`lint-output` pass is not semantic verification. Do not treat lint as a substitute for typechart/stat/mechanic/threataudit/itemthreatfit receipts.


## 8. Receipt-strict / no-mainline mechanic gate

Use before final output whenever prose contains mechanics, multipliers, stages, stat formulas, item effects, damage reasoning, or meta/common claims.

```bash
python3 scripts/verify.py receipt-strict <answer.md> <receipt.json>
```

Hard rules:

- Entity receipt is not mechanic receipt.
- If `mechanic` fails, exact numbers must be removed or downgraded to `08 description says ...`.
- Do not apply mainline Pokémon memory to Champions.
- Do not use manual stat formulas or EV/IV language.
- Damage receipts must show `modifier_breakdown` for STAB/type/weather/spread/item/ability.
- Damage input provenance must label meta/user/local fallback inputs; a local fallback calc is not a meta benchmark.

Fail/warn group:

```text
FAIL_ITEM_NOT_IN_LOCAL_DB
FAIL_ITEM_MECHANIC_CLAIM_WITHOUT_RECEIPT
FAIL_MAINLINE_MECHANIC_MEMORY_USED
FAIL_MECHANIC_STAGE_CLAIM_WITHOUT_RECEIPT
FAIL_MOVE_SEQUENCE_CLAIM_WITHOUT_MECHANIC_RECEIPT
FAIL_MOVE_SECONDARY_EFFECT_CLAIM_WITHOUT_RECEIPT
FAIL_WEATHER_MECHANIC_REASON_WITHOUT_RECEIPT
FAIL_MANUAL_STAT_FORMULA_USED
FAIL_META_CLAIM_WITHOUT_LIVE_SOURCE
FAIL_LOCAL_FALLBACK_WITHOUT_SEARCH_ATTEMPT
FAIL_DAMAGE_MULTIPLIER_HIDDEN
FAIL_DAMAGE_USED_UNVERIFIED_MECHANIC_MODIFIER
FAIL_DAMAGE_INPUT_PROVENANCE_MISSING
```

Examples that fail without exact receipts: Choice Scarf `×1.5 Spe`, Focus Sash “survives one hit”, Life Orb `×1.3`, Adaptability STAB `×2`, Drought “5 turns”, Sun/Rain damage multipliers, Last Respects exact scaling, Stamina `+1`, Heat Wave/Rock Slide secondary percentages, and any absent item such as Assault Vest, Clear Amulet, Choice Band, or Choice Specs.

## 9. Mechanic / interaction commands

```bash
python3 scripts/verify.py mechanic <mechanic_or_move>
python3 scripts/verify.py priority <pokemon> <move> [ability]
python3 scripts/verify.py interaction <scenario_json_or_path>
python3 scripts/verify.py boardscan <scenario_json_or_path>
python3 scripts/verify.py counterroute <scenario_json_or_path>
python3 scripts/verify.py mechanic-regression-tests
```

Use these for claims about priority, Prankster, Armor Tail, Soundproof, Pixilate, Mummy, Wandering Spirit, Gale Wings, No Guard, Electric Surge, Protect, Wide Guard, ally damage, contact effects, status effects, and hard-counter routes.

Do not infer from mainline memory. If the command returns `UNVERIFIED_MECHANIC`, remove or label the claim.

## 10. Type / typepassive / board commands

```bash
python3 scripts/verify.py typechart <attacking_type> <defender_pokemon_or_type_pair>
python3 scripts/verify.py type-regression-tests
python3 scripts/verify.py typepassive <scenario_json_or_path>
python3 scripts/verify.py typepassive-regression-tests
python3 scripts/verify.py boardscan <scenario_json_or_path>
```

Use `typechart` for multipliers. Use `typepassive` for type-wide passive/status/weather/hazard properties such as Fire burn immunity, Dark vs Prankster status, Rock in sand, Ice in snow, Ghost trapping immunity, Ground vs Thunder Wave, Poison/Steel poison immunity, and grounded Poison clearing Toxic Spikes.

## 11. Stat / speed / damage / sequence commands

```bash
python3 scripts/verify.py spread <json_or_text>
python3 scripts/verify.py stat <pokemon> <nature> <spread_json_or_text> [state_json]
python3 scripts/verify.py damage <scenario_json_or_path> [--require-complete-modifiers]
python3 scripts/verify.py sequence <scenario_json_or_path>
```

No displayed stat, KO, survival, damage roll, weather stat modifier, or staged-hit claim may be public without the matching receipt.

## 12. Render and card commands

```bash
python3 scripts/verify.py render <team.json>
python3 scripts/verify.py render <team.json> --platform claude
python3 scripts/verify.py render <team.json> --platform claude --style claude-html-card
python3 scripts/verify.py render <team.json> --platform claude --style card
python3 scripts/verify.py render <team.json> --style inline-ascii-card
python3 scripts/verify.py render <team.json> --style markdown-ascii-card
python3 scripts/verify.py ascii-assets
```

Default render is compact/no-card and must preserve verifier emoji. Offer a card after final answer only.

Card command policy:

- Claude + `--style card` / `--style claude-html-card` = canonical Claude HTML card only.
- Claude card output must use the canonical two-column HTML template; never ASCII box layout and never attached file output.
- In Claude, `claude-html-card` output is an HTML payload for the platform HTML/widget/artifact renderer. Do not paste raw `<div>` HTML into the chat text.
- Non-Claude/uncertain platform must not use or suggest Claude HTML. Use `--style inline-ascii-card` / `--style markdown-ascii-card` only after explicit card request, and print it inline in chat.
- Item ASCII remains disabled. Pokémon ASCII is visual only.

## 13. Lint and final self-audit

```bash
python3 scripts/verify.py lint-output <answer.md> <receipt.json>
python3 scripts/verify.py selfaudit <answer.md> <receipt.json>
python3 scripts/verify.py receipt-strict <answer.md> <receipt.json>
```

Workflow:

```text
draft → lint-output + receipt-strict → selfaudit → repair once → re-lint/re-strict → final
```

Do not add new claims during repair without a new receipt and re-lint.

## 14. Fail/warning code groups

Entity/public output:

```text
FAIL_PUBLIC_POKEMON_NOT_IN_01
FAIL_PUBLIC_POKEMON_WITHOUT_RECEIPT
FAIL_PUBLIC_MOVE_NOT_VERIFIED
FAIL_PUBLIC_ABILITY_NOT_VERIFIED
FAIL_PUBLIC_ITEM_NOT_VERIFIED
```

Type/typepassive:

```text
FAIL_TYPE_CLAIM_WITHOUT_TYPECHART_RECEIPT
FAIL_TYPE_PASSIVE_CLAIM_WITHOUT_RECEIPT
FAIL_STATUS_IMMUNITY_CLAIM_WITHOUT_TYPEPASSIVE_RECEIPT
FAIL_FIELD_HAZARD_IMMUNITY_CLAIM_WITHOUT_RECEIPT
FAIL_WEATHER_STAT_BOOST_CLAIM_WITHOUT_RECEIPT
```

Mechanic/board/counter:

```text
FAIL_MECHANIC_CLAIM_WITHOUT_RECEIPT
FAIL_ABILITY_INTERACTION_WITHOUT_INTERACTION_RECEIPT
FAIL_MECHANIC_CLAIM_WITHOUT_BOARDSCAN_RECEIPT
FAIL_COUNTER_RANK_WITHOUT_ROUTE_RECEIPTS
WARN_FORM_AMBIGUOUS_MEGA_RAICHU_X_Y
```

Stats/damage/render:

```text
FAIL_BASE_STAT_CLAIM_WITHOUT_01_RECEIPT
FAIL_BASE_STAT_CLAIM_CONFLICTS_01
FAIL_PUBLIC_RENDER_KO_CLAIM_WITHOUT_DAMAGE_RECEIPT
FAIL_PUBLIC_RENDER_RAW_SPREAD_UNLABELED
FAIL_PUBLIC_RENDER_EV_STYLE_252
```

Semantic audit/stat/item:

```text
FAIL_STAT_ADJECTIVE_WITHOUT_STAT_RECEIPT
FAIL_BULK_CLAIM_CONFLICTS_BASE_STATS
FAIL_MECHANIC_STAGE_CLAIM_WITHOUT_RECEIPT
FAIL_MOVE_SEQUENCE_CLAIM_WITHOUT_MECHANIC_RECEIPT
FAIL_08_DESCRIPTION_OVERINTERPRETED
FAIL_RISK_SECTION_WITHOUT_THREAT_AUDIT
FAIL_ITEM_REASON_WITHOUT_ITEMTHREATFIT_RECEIPT
FAIL_ITEM_THREAT_PROFILE_MISSING
FAIL_ITEM_REASON_IGNORES_HIGHER_BOARD_RISK
WARN_RESIST_BERRY_SELECTED_FROM_SINGLE_WEAKNESS
WARN_ITEM_MISALIGNED_WITH_BOARD_THREAT
```

Speed/lead planning:

```text
FAIL_SPEED_MODE_CLAIM_WITHOUT_SPEEDPLAN_RECEIPT
FAIL_TRICK_ROOM_RECOMMENDATION_WITHOUT_BENEFICIARY_CHECK
FAIL_LEAD_PLAN_WITHOUT_TURN_SIMULATION
WARN_DUAL_SPEED_MODE_CONFLICT
WARN_TRICK_ROOM_MAY_HELP_OPPONENT
WARN_TRICK_ROOM_BACKUP_NOT_MAIN_MODE
WARN_FAST_MON_HURT_BY_TRICK_ROOM
```

Meta baseline/actionable:

```text
FAIL_ACTIONABLE_ITEM_RECOMMENDATION_WITHOUT_META_BASELINE
FAIL_META_DIRECT_WITHOUT_SOURCE
FAIL_ITEMTHREATFIT_USED_AS_META_BASELINE
FAIL_LOCAL_FALLBACK_WITHOUT_SEARCH_ATTEMPT
FAIL_META_BASELINE_SLOT_MISSING
```


### v29.39 card/emoji receipt checks

- `render --platform claude --style card` maps to the canonical Claude HTML card only and must be displayed through the platform HTML/widget/artifact renderer, not raw chat text.
- Move chips must copy `move.display` with type emoji.
- Type labels must use verifier type display, e.g. `🌿 Grass / 👻 Ghost`, not bare `Grass/Ghost`.
- `lint-output` may fail `FAIL_PUBLIC_RENDER_MISSING_MOVE_EMOJI` or `FAIL_PUBLIC_RENDER_MISSING_TYPE_EMOJI` when public output drops emoji.

## v29.41 lint precision notes

`verify.py stat` now returns `nature_effect` and render/card output must use `nature_display` such as `Jolly (+Spe / -SpA)`.

Receipt-strict guards should distinguish:

- audit/caveat prose from recommendations;
- common words from entity names (`Trick Room` ≠ move `Trick`, prose “pressure” ≠ ability `Pressure`);
- typechart immunity such as `Ground → Fire/Flying = 0x` from typepassive immunity;
- `threataudit.board_risks` from missing boardscan when the claim is only a board-risk warning;
- workflow phrase `meta baseline` from unsupported live meta claims.

New/updated warnings:

```text
WARN_EV_LABEL_USE_INVESTMENT
WARN_NATURE_EFFECT_NOT_DISPLAYED
```

`252 EV`/`IV` remains a hard failure. Simple `EVs` wording is repaired to `spread` / `investment` unless the user is quoting raw input.



## v29.42 structured mechanic data

New data files:

```text
data/10_structured_mechanic_receipts.jsonl
data/10_entity_manifest_current.json
```

New commands:

```bash
python3 scripts/verify.py mechanic-data-lint
python3 scripts/verify.py mechanic-coverage
python3 scripts/verify.py mechanic-effect <entity_name> --context damage
python3 scripts/verify.py damage <scenario.json> --require-complete-modifiers
```

Rules:

- Receipt-strict remains active: no receipt = no claim.
- v29.42 adds structured receipts; it does not parse 08 prose into numbers at runtime.
- Any structured move/item/ability receipt referencing an entity absent from current 08 fails `mechanic-data-lint`.
- All current 08 moves/items/abilities must have classification coverage.
- Complete public OHKO/2HKO/survival claims require `damage_completeness=complete` and `public_ko_claim_allowed=true`.
- Partial damage receipts must be described as partial/lower-bound and cannot support guaranteed KO/survival claims.
- Do not add convenience mechanics for items absent from current 08; for this pack, Choice Band and Choice Specs are absent and remain blocked.

### v29.44 action-matrix lint gates

```text
FAIL_SWITCH_RECOMMENDATION_WITHOUT_ACTION_MATRIX
FAIL_AMBIGUOUS_TYPE_TABLE_DIRECTION
FAIL_DEFENSIVE_MATRIX_CELL_MISSING_TAKEN
FAIL_OFFENSIVE_MATRIX_CELL_MISSING_DEALT
FAIL_AMBIGUOUS_ATTACK_DEFENSE_TABLE
FAIL_MATRIX_RECEIPT_MISSING_DIRECTION
```

These gates prevent public prose from choosing switch-ins or presenting type tables without explicit direction and `taken`/`dealt` cell semantics.


## v29.45 readable battle report commands

### battle-report-template

```bash
python3 scripts/verify.py battle-report-template --style standard
```

Returns the required sections for readable battle-log analysis. Styles: `compact`, `standard`, `deep`.

### battle-report-render

```bash
python3 scripts/verify.py battle-report-render report.json --style standard
```

Renders a structured report JSON into Markdown. This renderer does not parse raw battle logs or invent mechanics; it only formats supplied structured facts.

### battle-report-lint

```bash
python3 scripts/verify.py battle-report-lint answer.md receipt.json --style standard
```

Checks battle report readability and receipt discipline:

- verdict/winner/main reason appears early;
- key mistakes and turn references are present;
- switch/swap advice has `SWITCH_SAFETY_MATRIX` or `INCOMING_DEFENSE_MATRIX`;
- type/switch tables include a direction line and `taken`/`dealt` semantics;
- raw receipt JSON is not dumped in public output;
- scores include nearby reasons;
- OHKO/2HKO/guaranteed/survival claims require complete damage receipts.

Observed damage percentages from the battle log may be quoted as observed/log damage. They are not damage-calc receipts and must not be upgraded into guaranteed KO/survival claims without `damage_completeness=complete`.

New report lint failures:

```text
FAIL_BATTLE_REPORT_MISSING_VERDICT
FAIL_BATTLE_REPORT_MISSING_KEY_MISTAKES
FAIL_BATTLE_REPORT_MISSING_TURN_REFERENCES
FAIL_BATTLE_REPORT_DUMPS_RAW_RECEIPT_JSON
FAIL_BATTLE_REPORT_SWITCH_ADVICE_WITHOUT_MATRIX
FAIL_BATTLE_REPORT_TYPE_TABLE_MISSING_DIRECTION
FAIL_BATTLE_REPORT_TOO_LONG_FOR_STYLE
FAIL_BATTLE_REPORT_SCORE_WITHOUT_REASON
FAIL_BATTLE_REPORT_DAMAGE_CLAIM_WITHOUT_COMPLETE_DAMAGE_RECEIPT
```


### v29.46 fail codes

```text
FAIL_ACTIONABLE_ITEM_RECOMMENDATION_WITHOUT_META_BASELINE
FAIL_ACTIONABLE_MOVE_RECOMMENDATION_WITHOUT_META_BASELINE
FAIL_ACTIONABLE_SPREAD_RECOMMENDATION_WITHOUT_META_BASELINE
FAIL_LOCAL_FALLBACK_WITHOUT_SEARCH_ATTEMPT
FAIL_ITEMTHREATFIT_USED_AS_META_BASELINE
FAIL_ITEM_CLAUSE_REPAIR_USED_AS_FINAL_RECOMMENDATION
FAIL_LOCAL_TEAM_FIT_USED_AS_FINAL_RECOMMENDATION
FAIL_LOCAL_BENCHMARK_OVERRIDE_WITHOUT_DIFF
FAIL_META_BASELINE_SLOT_MISSING
FAIL_META_BASELINE_SOURCE_NOT_APPROVED
```
