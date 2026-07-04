"""Regression helpers for PokeCham verifier."""
from __future__ import annotations

from pathlib import Path

from . import legacy
from .switch_matrix import verify_switch_safety_matrix
from .report_lint import battle_report_lint
from .meta_baseline import meta_baseline_gate, meta_baseline_lint
from .recommendation_lint import recommendation_provenance_lint
from .type_matrix import verify_incoming_defense_matrix


def _fixture_path(*parts: str) -> Path:
    return Path(__file__).resolve().parents[2].joinpath(*parts)


def run_all_regression_tests() -> dict:
    checks = []
    failures = []

    def add(name: str, receipt: dict, expected_status: str = "pass"):
        checks.append({"name": name, "receipt": receipt})
        if receipt.get("status") != expected_status:
            failures.append({"name": name, "expected": expected_status, "actual": receipt.get("status"), "receipt": receipt})

    add("mechanic-data-lint", legacy.verify_mechanic_data_lint())
    add("mechanic-coverage", legacy.verify_mechanic_coverage())

    # Mirror existing CLI regression intent without shelling out.
    type_cases = [
        ("Ghost", "Dark", 0.5, "resisted"),
        ("Ghost", "Normal", 0.0, "immune"),
        ("Ghost", "Dark/Normal", 0.0, "immune"),
        ("Fire", "Steel/Dragon", 1.0, "neutral"),
        ("Ground", "Flying", 0.0, "immune"),
        ("Ground", "Sinistcha", 0.5, "resisted"),
        ("Fire", "Kingambit", 2.0, "super_effective"),
    ]
    type_failures = []
    type_receipts = []
    for atk, defender, expected, label in type_cases:
        rec = legacy.verify_type_effectiveness(atk, defender)
        type_receipts.append(rec)
        if rec.get("status") != "pass" or float(rec.get("total_type_multiplier", -1)) != expected or rec.get("label") != label:
            type_failures.append({"case": f"{atk} -> {defender}", "expected": expected, "expected_label": label, "receipt": rec})
    add("type-regression-tests", {"mode": "type_regression_tests", "status": "pass" if not type_failures else "fail", "receipts": type_receipts, "failures": type_failures})

    typepassive_cases = [
        {"name": "Dark blocks opposing Prankster Taunt", "scenario": {"defender": {"types": ["Dark"]}, "incoming": {"move": "Taunt", "category": "Status", "source_ability": "Prankster", "side": "opponent"}}, "expect": "pass"},
        {"name": "Ground blocks Thunder Wave", "scenario": {"defender": {"types": ["Ground"]}, "incoming": {"move": "Thunder Wave"}}, "expect": "pass"},
    ]
    tpass_failures = []
    tpass_receipts = []
    for c in typepassive_cases:
        rec = legacy.verify_typepassive(c["scenario"])
        tpass_receipts.append({"name": c["name"], "receipt": rec})
        if rec.get("status") != c["expect"]:
            tpass_failures.append({"case": c["name"], "expected": c["expect"], "actual": rec.get("status"), "receipt": rec})
    add("typepassive-regression-tests", {"mode": "typepassive_regression_tests", "status": "pass" if not tpass_failures else "fail", "receipts": tpass_receipts, "failures": tpass_failures})

    mechanic_cases = [
        {"name": "Intimidate vs Contrary", "scenario": {"actor": {"ability": "Intimidate"}, "target": {"ability": "Contrary"}}, "expect": "pass"},
        {"name": "Pixilate Hyper Voice", "scenario": {"actor": {"ability": "Pixilate", "move": "Hyper Voice"}}, "expect": "pass"},
    ]
    mech_failures = []
    mech_receipts = []
    for c in mechanic_cases:
        rec = legacy.verify_interaction(c["scenario"])
        mech_receipts.append({"name": c["name"], "receipt": rec})
        if rec.get("status") != c["expect"]:
            mech_failures.append({"case": c["name"], "expected": c["expect"], "actual": rec.get("status"), "receipt": rec})
    add("mechanic-regression-tests", {"mode": "mechanic_regression_tests", "status": "pass" if not mech_failures else "fail", "receipts": mech_receipts, "failures": mech_failures})

    # v29.44 direction-explicit matrix regressions.
    type_team = legacy._load_json_arg(str(_fixture_path("tests", "fixtures", "teams", "type_matrix_sinistcha.json")))
    incoming = verify_incoming_defense_matrix(type_team)
    ground_sin = ((incoming.get("rows") or {}).get("Sinistcha") or {}).get("Ground") or {}
    if incoming.get("status") != "pass" or ground_sin.get("value_display") != "0.5x taken":
        failures.append({"name": "incoming-defense-matrix-ground-sinistcha", "expected": "0.5x taken", "actual": ground_sin, "receipt": incoming})
    checks.append({"name": "incoming-defense-matrix-ground-sinistcha", "receipt": incoming})

    board = legacy._load_json_arg(str(_fixture_path("tests", "fixtures", "boards", "switch_charizard_weatherball_vs_p2.json")))
    switch = verify_switch_safety_matrix(board)
    expected_switch = {
        ("Kingambit", "Charizard-Mega-Y / Weather Ball [Fire]"): "2x taken",
        ("Sylveon", "Charizard-Mega-Y / Weather Ball [Fire]"): "1x taken",
        ("Dragonite", "Tyranitar / Rock Slide [Rock]"): "2x taken",
        ("Garchomp", "Charizard-Mega-Y / Thunderbolt [Electric]"): "0x taken",
    }
    switch_failures = []
    rows = switch.get("rows") or {}
    for (mon, move_label), expected in expected_switch.items():
        got = (((rows.get(mon) or {}).get("incoming_moves") or {}).get(move_label) or {}).get("value_display")
        if got != expected:
            switch_failures.append({"case": f"{mon} vs {move_label}", "expected": expected, "actual": got})
    if switch.get("status") != "pass" or switch_failures:
        failures.append({"name": "switch-safety-matrix-charizard-weatherball", "expected": "pass", "actual": switch.get("status"), "matrix_failures": switch_failures, "receipt": switch})
    checks.append({"name": "switch-safety-matrix-charizard-weatherball", "receipt": switch, "matrix_failures": switch_failures})

    # v29.44 lint gates: switch advice without matrix must fail; same advice with
    # a switch matrix receipt must pass hard failures.
    bad_answer = _fixture_path("tests", "fixtures", "answers", "answer_bad_switch_no_matrix.md")
    good_answer = _fixture_path("tests", "fixtures", "answers", "answer_good_switch_with_matrix.md")
    empty_receipt = _fixture_path("tests", "receipts", "receipt_empty.json")
    switch_receipt = _fixture_path("tests", "receipts", "receipt_switch_safety_charizard_weatherball.json")
    bad_lint = legacy.lint_public_output(bad_answer.read_text(), legacy._load_json_arg(str(empty_receipt)))
    good_lint = legacy.lint_public_output(good_answer.read_text(), legacy._load_json_arg(str(switch_receipt)))
    bad_codes = {f.get("code") for f in bad_lint.get("failures", [])}
    if "FAIL_SWITCH_RECOMMENDATION_WITHOUT_ACTION_MATRIX" not in bad_codes:
        failures.append({"name": "lint-switch-without-matrix", "expected_code": "FAIL_SWITCH_RECOMMENDATION_WITHOUT_ACTION_MATRIX", "receipt": bad_lint})
    if good_lint.get("status") != "pass":
        failures.append({"name": "lint-switch-with-matrix", "expected": "pass", "actual": good_lint.get("status"), "receipt": good_lint})
    checks.append({"name": "lint-switch-without-matrix", "receipt": bad_lint})
    checks.append({"name": "lint-switch-with-matrix", "receipt": good_lint})



    # v29.45 readable battle report output lint regressions.
    good_report = _fixture_path("tests", "fixtures", "reports", "report_good_standard.md")
    bad_no_matrix = _fixture_path("tests", "fixtures", "reports", "report_bad_switch_no_matrix.md")
    bad_ambiguous = _fixture_path("tests", "fixtures", "reports", "report_bad_ambiguous_table.md")
    bad_receipt_dump = _fixture_path("tests", "fixtures", "reports", "report_bad_too_verbose_receipt_dump.md")
    good_receipt = _fixture_path("tests", "receipts", "receipt_battle_report_charizard_weatherball.json")
    empty = _fixture_path("tests", "receipts", "receipt_empty.json")
    report_good_lint = battle_report_lint(good_report.read_text(), legacy._load_json_arg(str(good_receipt)), style="standard")
    report_bad_no_matrix = battle_report_lint(bad_no_matrix.read_text(), legacy._load_json_arg(str(empty)), style="standard")
    report_bad_ambiguous = battle_report_lint(bad_ambiguous.read_text(), legacy._load_json_arg(str(good_receipt)), style="standard")
    report_bad_dump = battle_report_lint(bad_receipt_dump.read_text(), legacy._load_json_arg(str(good_receipt)), style="standard")
    if report_good_lint.get("status") != "pass":
        failures.append({"name": "battle-report-good-standard", "expected": "pass", "actual": report_good_lint.get("status"), "receipt": report_good_lint})
    bad_no_matrix_codes = {f.get("code") for f in report_bad_no_matrix.get("failures", [])}
    if "FAIL_BATTLE_REPORT_SWITCH_ADVICE_WITHOUT_MATRIX" not in bad_no_matrix_codes:
        failures.append({"name": "battle-report-bad-switch-no-matrix", "expected_code": "FAIL_BATTLE_REPORT_SWITCH_ADVICE_WITHOUT_MATRIX", "receipt": report_bad_no_matrix})
    bad_ambiguous_codes = {f.get("code") for f in report_bad_ambiguous.get("failures", [])}
    if "FAIL_BATTLE_REPORT_TYPE_TABLE_MISSING_DIRECTION" not in bad_ambiguous_codes:
        failures.append({"name": "battle-report-bad-ambiguous-table", "expected_code": "FAIL_BATTLE_REPORT_TYPE_TABLE_MISSING_DIRECTION", "receipt": report_bad_ambiguous})
    bad_dump_codes = {f.get("code") for f in report_bad_dump.get("failures", [])}
    if "FAIL_BATTLE_REPORT_DUMPS_RAW_RECEIPT_JSON" not in bad_dump_codes:
        failures.append({"name": "battle-report-bad-receipt-dump", "expected_code": "FAIL_BATTLE_REPORT_DUMPS_RAW_RECEIPT_JSON", "receipt": report_bad_dump})
    checks.append({"name": "battle-report-good-standard", "receipt": report_good_lint})
    checks.append({"name": "battle-report-bad-switch-no-matrix", "receipt": report_bad_no_matrix})
    checks.append({"name": "battle-report-bad-ambiguous-table", "receipt": report_bad_ambiguous})
    checks.append({"name": "battle-report-bad-receipt-dump", "receipt": report_bad_dump})



    # v29.46 meta-baseline hardgate regressions.
    mb_dir = _fixture_path("tests", "fixtures", "meta_baseline")
    ans_dir = _fixture_path("tests", "fixtures", "answers")
    rec_dir = _fixture_path("tests", "receipts")
    team_whiteherb = legacy._load_json_arg(str(mb_dir / "team_dragonite_whiteherb.json"))
    team_wacan = legacy._load_json_arg(str(mb_dir / "team_dragonite_wacan.json"))
    team_sinistcha = legacy._load_json_arg(str(mb_dir / "team_sinistcha_sitrus.json"))
    meta_good = legacy._load_json_arg(str(mb_dir / "meta_good_dragonite_item.json"))
    meta_bluestacks = legacy._load_json_arg(str(mb_dir / "meta_bad_bluestacks.json"))
    meta_missing_search = legacy._load_json_arg(str(mb_dir / "meta_missing_search_attempt.json"))
    meta_fallback = legacy._load_json_arg(str(mb_dir / "meta_local_fallback_after_search.json"))
    meta_override = legacy._load_json_arg(str(mb_dir / "meta_benchmark_override_with_diff.json"))
    meta_override_bad = legacy._load_json_arg(str(mb_dir / "meta_benchmark_override_without_diff.json"))
    meta_itemthreatfit = legacy._load_json_arg(str(mb_dir / "meta_itemthreatfit_only.json"))

    mb_good_lint = meta_baseline_lint(meta_good)
    mb_bad_source = meta_baseline_lint(meta_bluestacks)
    mb_missing_search = meta_baseline_lint(meta_missing_search)
    mb_fallback_lint = meta_baseline_lint(meta_fallback)
    mb_override_lint = meta_baseline_lint(meta_override)
    mb_override_bad_lint = meta_baseline_lint(meta_override_bad)
    mb_itemthreatfit_lint = meta_baseline_lint(meta_itemthreatfit)
    mb_good_gate = meta_baseline_gate(team_whiteherb, meta_good)
    mb_wacan_fail = meta_baseline_gate(team_wacan, meta_good, fields=["item"])
    mb_fallback_gate = meta_baseline_gate(team_sinistcha, meta_fallback)
    mb_override_gate = meta_baseline_gate(team_wacan, meta_override)

    if mb_good_lint.get("status") != "pass" or mb_good_gate.get("status") != "pass":
        failures.append({"name": "meta-baseline-good-direct", "expected": "pass", "lint": mb_good_lint, "gate": mb_good_gate})
    if "FAIL_META_BASELINE_SOURCE_NOT_APPROVED" not in {f.get("code") for f in mb_bad_source.get("failures", [])}:
        failures.append({"name": "meta-baseline-blocked-source", "expected_code": "FAIL_META_BASELINE_SOURCE_NOT_APPROVED", "receipt": mb_bad_source})
    if "FAIL_LOCAL_FALLBACK_WITHOUT_SEARCH_ATTEMPT" not in {f.get("code") for f in mb_missing_search.get("failures", [])}:
        failures.append({"name": "meta-baseline-missing-search-attempt", "expected_code": "FAIL_LOCAL_FALLBACK_WITHOUT_SEARCH_ATTEMPT", "receipt": mb_missing_search})
    if mb_fallback_lint.get("status") != "pass" or mb_fallback_gate.get("status") != "pass":
        failures.append({"name": "meta-baseline-local-fallback-after-search", "expected": "pass", "lint": mb_fallback_lint, "gate": mb_fallback_gate})
    if mb_override_lint.get("status") != "pass" or mb_override_gate.get("status") != "pass":
        failures.append({"name": "meta-baseline-benchmark-override", "expected": "pass", "lint": mb_override_lint, "gate": mb_override_gate})
    if "FAIL_LOCAL_BENCHMARK_OVERRIDE_WITHOUT_DIFF" not in {f.get("code") for f in mb_override_bad_lint.get("failures", [])}:
        failures.append({"name": "meta-baseline-override-without-diff", "expected_code": "FAIL_LOCAL_BENCHMARK_OVERRIDE_WITHOUT_DIFF", "receipt": mb_override_bad_lint})
    if "FAIL_ITEMTHREATFIT_USED_AS_META_BASELINE" not in {f.get("code") for f in mb_itemthreatfit_lint.get("failures", [])}:
        failures.append({"name": "meta-baseline-itemthreatfit-only", "expected_code": "FAIL_ITEMTHREATFIT_USED_AS_META_BASELINE", "receipt": mb_itemthreatfit_lint})
    if "FAIL_ACTIONABLE_ITEM_RECOMMENDATION_WITHOUT_META_BASELINE" not in {f.get("code") for f in mb_wacan_fail.get("failures", [])}:
        failures.append({"name": "meta-baseline-wacan-without-meta", "expected_code": "FAIL_ACTIONABLE_ITEM_RECOMMENDATION_WITHOUT_META_BASELINE", "receipt": mb_wacan_fail})

    rec_bad_wacan = recommendation_provenance_lint((ans_dir / "answer_bad_wacan_without_meta.md").read_text(), mb_wacan_fail)
    rec_bad_widelens = recommendation_provenance_lint((ans_dir / "answer_bad_wide_lens_itemclause_only.md").read_text(), legacy._load_json_arg(str(rec_dir / "receipt_empty.json")))
    rec_good_override = recommendation_provenance_lint((ans_dir / "answer_good_benchmark_override.md").read_text(), mb_override_gate)
    if rec_good_override.get("status") != "pass":
        failures.append({"name": "recommendation-provenance-good-override", "expected": "pass", "receipt": rec_good_override})
    if "FAIL_ACTIONABLE_RECOMMENDATION_WITH_FAILED_META_BASELINE_GATE" not in {f.get("code") for f in rec_bad_wacan.get("failures", [])}:
        failures.append({"name": "recommendation-provenance-bad-wacan", "expected_code": "FAIL_ACTIONABLE_RECOMMENDATION_WITH_FAILED_META_BASELINE_GATE", "receipt": rec_bad_wacan})
    if "FAIL_ACTIONABLE_RECOMMENDATION_WITHOUT_META_BASELINE_GATE" not in {f.get("code") for f in rec_bad_widelens.get("failures", [])}:
        failures.append({"name": "recommendation-provenance-bad-widelens", "expected_code": "FAIL_ACTIONABLE_RECOMMENDATION_WITHOUT_META_BASELINE_GATE", "receipt": rec_bad_widelens})

    checks.extend([
        {"name": "meta-baseline-good-direct", "receipt": mb_good_gate},
        {"name": "meta-baseline-blocked-source", "receipt": mb_bad_source},
        {"name": "meta-baseline-local-fallback-after-search", "receipt": mb_fallback_gate},
        {"name": "meta-baseline-benchmark-override", "receipt": mb_override_gate},
        {"name": "meta-baseline-wacan-without-meta", "receipt": mb_wacan_fail},
        {"name": "recommendation-provenance-bad-wacan", "receipt": rec_bad_wacan},
        {"name": "recommendation-provenance-good-override", "receipt": rec_good_override},
    ])

    return {
        "mode": "all_regression_tests",
        "status": "pass" if not failures else "fail",
        "checks": checks,
        "failures": failures,
        "rule": "Run before and after verifier refactors. v29.46 preserves CLI compatibility, v29.44 action matrices, v29.45 battle reports, and adds meta-baseline hard gates.",
    }
