# v29.42 — mechanicdata complete damage engine release notes

## Purpose

v29.42 keeps receipt-strict behavior but adds current-DB-only structured mechanic data so `verify.py damage` can apply verified item, ability, weather, move-dynamic, and defender-item modifiers instead of remaining a permanent lower-bound calculator.

## New data

- `data/10_structured_mechanic_receipts.jsonl`
- `data/10_entity_manifest_current.json`

Current DB guard counts from `08_global_moves_abilities_items.csv`:

- moves: 937/937 classified
- abilities: 313/313 classified
- items: 148/148 classified

## New/updated commands

```bash
python3 scripts/verify.py mechanic-data-lint
python3 scripts/verify.py mechanic-coverage
python3 scripts/verify.py mechanic-effect "Life Orb" --context damage
python3 scripts/verify.py damage <scenario.json> --require-complete-modifiers
```

## Hard rules

- No receipt = no claim remains active.
- No runtime parsing of `08` description text into numeric effects.
- Any move/item/ability mechanic receipt referencing an entity absent from current `08` fails `mechanic-data-lint`.
- Public OHKO/2HKO/survival claims require `damage_completeness=complete` and `public_ko_claim_allowed=true`.
- Partial receipts are lower-bound/incomplete only.
- Do not add convenience mechanics for absent items. In this pack, `Choice Band`, `Choice Specs`, `Clear Amulet`, and `Assault Vest` remain blocked.

## Verification snapshot

These were run during packaging:

```text
mechanic-data-lint: pass
mechanic-coverage: pass — items 148/148, moves 937/937, abilities 313/313
type-regression-tests: pass
typepassive-regression-tests: pass
mechanic-regression-tests: pass
Life Orb complete damage fixture: pass
Weather Ball + sun complete damage fixture: pass
Tough Claws missing contact flag complete-mode fixture: fail as expected
```
