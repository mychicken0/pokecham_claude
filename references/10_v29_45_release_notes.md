# v29.45 — readable battle report output

Purpose: make verified battle-log analysis readable without weakening receipt-strict rules.

## Added

- `report_engine.py` for structured battle report Markdown rendering.
- `report_lint.py` for battle report readability and receipt gates.
- Commands:
  - `python3 scripts/verify.py battle-report-template --style standard`
  - `python3 scripts/verify.py battle-report-render report.json --style standard`
  - `python3 scripts/verify.py battle-report-lint answer.md receipt.json --style standard`
- Fixtures for the Charizard Weather Ball / Sylveon switch regression.

## Preserved

- v29.42 structured mechanic data and complete damage gate.
- v29.43 CLI facade and regression command.
- v29.44 direction-explicit action matrices and switch/swap gates.

## Rules

- Battle reports should be verdict-first and evidence-gated.
- Public reports summarize receipts; they do not dump raw JSON.
- Observed battle-log damage percentages are allowed only as observed/log damage.
- OHKO/2HKO/guaranteed survival claims still require complete damage receipts.
- No Pokémon/move/item/ability entities were added in this release.
