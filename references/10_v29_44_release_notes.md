# v29.44 — action matrix / switch gate

Purpose: prevent attacker/defender type-direction mistakes in battle advice.

## Added

- `incoming-defense-matrix`: `ENEMY MOVE TYPE → OUR DEFENDER`, cells are `x taken`.
- `outgoing-attack-matrix`: `OUR MOVE → ENEMY DEFENDER`, cells are `x dealt`.
- `switch-safety-matrix`: `ENEMY LIKELY MOVE → OUR SWITCH-IN`, cells are `x taken`.
- `all-regression-tests` now checks `Fire → Kingambit = 2x taken` in switch context and `Ground → Sinistcha = 0.5x taken`.

## Lint gates

- Switch/swap/pivot advice without switch/incoming matrix fails.
- Matrix tables without direction line fail.
- Incoming/switch cells without `taken` fail.
- Outgoing cells without `dealt` fail.

## Compatibility

Existing `python3 scripts/verify.py ...` commands remain valid. No new Pokémon, move, item, or ability entities were added.
