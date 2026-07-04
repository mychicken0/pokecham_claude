#!/usr/bin/env bash
set -euo pipefail
python3 scripts/verify.py mechanic-data-lint >/dev/null
python3 scripts/verify.py mechanic-coverage >/dev/null
python3 scripts/verify.py all-regression-tests >/dev/null
python3 scripts/verify.py type-matrix tests/fixtures/teams/type_matrix_sinistcha.json >/dev/null
