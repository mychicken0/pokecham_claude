# v29.43 — Refactor, Type Matrix, Doc Cleanup

## Purpose

- Keep the public verifier command stable while moving implementation behind `scripts/pokecham_verify/`.
- Add `type-matrix` receipts to prevent unverified type matchup claims such as missed dual-type resistance multiplication.
- Keep markdown docs concise: policy in references, mechanics in structured data, enforcement in verifier code, examples in test fixtures.

## Compatibility

Existing commands remain valid:

```bash
python3 scripts/verify.py <command> ...
```

`verify.py` is now a 13-line CLI facade. v29.42 behavior is preserved through `scripts/pokecham_verify/legacy.py`; v29.43 adds new package seams for future safe extraction.

## New commands

```bash
python3 scripts/verify.py type-matrix <team.json> [targets.json]
python3 scripts/verify.py all-regression-tests
```

## Data policy

No new Pokémon, moves, items, or abilities were added. v29.42 current-DB-only guard remains active. Mechanic receipts referencing absent current-08 entities still fail.

## Public-answer rule

Type matchup, weakness, resistance, immunity, and coverage claims require direct `typechart`, `type-matrix`, or damage typechart provenance. KO/survival claims still require complete damage receipts.
