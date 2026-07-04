#!/usr/bin/env bash
set -euo pipefail

python3 scripts/verify.py mechanic-data-lint
python3 scripts/verify.py mechanic-coverage
python3 scripts/verify.py all-regression-tests
python3 scripts/verify.py incoming-defense-matrix tests/fixtures/teams/type_matrix_sinistcha.json >/dev/null
python3 scripts/verify.py switch-safety-matrix tests/fixtures/boards/switch_charizard_weatherball_vs_p2.json >/dev/null
python3 scripts/verify.py lint-output tests/fixtures/answers/answer_good_switch_with_matrix.md tests/receipts/receipt_switch_safety_charizard_weatherball.json >/dev/null
