# v29.46 — meta-baseline hardgate + doc order

Purpose: prevent local verifier, itemthreatfit, or Item Clause repair from becoming final item/move/spread/nature/ability recommendations without player/meta evidence.

## Added

- `scripts/pokecham_verify/meta_baseline.py`
- `scripts/pokecham_verify/recommendation_lint.py`
- `python3 scripts/verify.py meta-baseline-lint meta_baseline.json`
- `python3 scripts/verify.py meta-baseline-gate team.json meta_baseline.json`
- `python3 scripts/verify.py recommendation-provenance-lint answer.md receipt.json`

## Policy

- `itemthreatfit` proves fit, not recommendation eligibility.
- `ITEM_CLAUSE_REPAIR` is intermediate, not final evidence.
- `LOCAL_FALLBACK_AFTER_SEARCH` requires a matching approved no-result/unavailable search attempt.
- `LOCAL_BENCHMARK_OVERRIDE` requires explicit diff from the meta baseline.
- Blocked sources such as BlueStacks cannot satisfy meta baseline receipts.

## Data scope

No Pokémon, move, item, ability, or mechanic entities were added. v29.46 is a workflow/enforcement release only.
