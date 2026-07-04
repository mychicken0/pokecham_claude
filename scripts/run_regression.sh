#!/usr/bin/env bash
set -euo pipefail

python3 scripts/verify.py mechanic-data-lint
python3 scripts/verify.py mechanic-coverage
python3 scripts/verify.py all-regression-tests
python3 scripts/verify.py incoming-defense-matrix tests/fixtures/teams/type_matrix_sinistcha.json >/dev/null
python3 scripts/verify.py switch-safety-matrix tests/fixtures/boards/switch_charizard_weatherball_vs_p2.json >/dev/null
python3 scripts/verify.py lint-output tests/fixtures/answers/answer_good_switch_with_matrix.md tests/receipts/receipt_switch_safety_charizard_weatherball.json >/dev/null
python3 scripts/verify.py battle-report-lint tests/fixtures/reports/report_good_standard.md tests/receipts/receipt_battle_report_charizard_weatherball.json --style standard >/dev/null
python3 scripts/verify.py meta-baseline-lint tests/fixtures/meta_baseline/meta_good_dragonite_item.json >/dev/null
python3 scripts/verify.py meta-baseline-gate tests/fixtures/meta_baseline/team_dragonite_whiteherb.json tests/fixtures/meta_baseline/meta_good_dragonite_item.json >/dev/null
python3 scripts/verify.py recommendation-provenance-lint tests/fixtures/answers/answer_good_benchmark_override.md tests/receipts/receipt_meta_gate_dragonite_wacan_override.json >/dev/null
