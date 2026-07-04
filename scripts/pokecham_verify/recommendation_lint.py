"""v29.46 public recommendation provenance lint."""
from __future__ import annotations

import re
from typing import Any

RECOMMENDATION_LINT_VERSION = "v29.46-meta-baseline-hardgate-docorder"

ACTIONABLE_RE = re.compile(r"(?i)(recommend|แนะนำ|ควรใช้|ควรเปลี่ยน|ใส่|ใช้เป็น|final team|ทีมสุดท้าย|set สุดท้าย|best|standard|meta|เมต้า|เหมาะสุด)")
ITEM_RE = re.compile(r"(?i)(item|ไอเทม|berry|sitrus|chople|wacan|wide\s*lens|white\s*herb|leftovers|focus\s*sash|life\s*orb|choice\s*scarf)")
MOVE_RE = re.compile(r"(?i)(move|ท่า|moves)")
SPREAD_RE = re.compile(r"(?i)(spread|investment|สเปรด|ลงทุน|EVs?)")
LOCAL_FIT_RE = re.compile(r"(?i)(itemthreatfit|item\s*clause\s*repair|LOCAL_TEAM_FIT|LOCAL_FALLBACK(?!_AFTER_SEARCH)|ITEM_CLAUSE_REPAIR|Wacan\s+Berry|Wide\s+Lens)")
RECEIPT_JSON_RE = re.compile(r"(?i)(\"mode\"\s*:\s*\"meta_baseline_gate\"|\"public_recommendation_allowed\"\s*:|\"slot_baseline_count\"\s*:)")


def _find_meta_gate(receipt: dict | None) -> dict | None:
    if not isinstance(receipt, dict):
        return None
    if receipt.get("mode") == "meta_baseline_gate":
        return receipt
    for key in ("meta_baseline_gate", "recommendation_provenance", "meta_gate"):
        val = receipt.get(key)
        if isinstance(val, dict) and val.get("mode") == "meta_baseline_gate":
            return val
    for val in receipt.values():
        if isinstance(val, dict):
            found = _find_meta_gate(val)
            if found:
                return found
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    found = _find_meta_gate(item)
                    if found:
                        return found
    return None


def recommendation_provenance_lint(answer_text: str, receipt: dict | None = None) -> dict:
    text = str(answer_text or "")
    receipt = receipt or {}
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    gate = _find_meta_gate(receipt)
    actionable = bool(ACTIONABLE_RE.search(text))
    mentions_slot = bool(ITEM_RE.search(text) or MOVE_RE.search(text) or SPREAD_RE.search(text))

    if RECEIPT_JSON_RE.search(text):
        failures.append({"code": "FAIL_RECOMMENDATION_DUMPS_RAW_META_RECEIPT_JSON", "detail": "Public recommendation should summarize provenance, not dump raw meta gate JSON."})

    if actionable and mentions_slot:
        if not gate:
            failures.append({"code": "FAIL_ACTIONABLE_RECOMMENDATION_WITHOUT_META_BASELINE_GATE", "detail": "Actionable item/move/spread recommendation requires meta-baseline-gate receipt."})
        elif gate.get("status") != "pass" or gate.get("public_recommendation_allowed") is not True:
            failures.append({"code": "FAIL_ACTIONABLE_RECOMMENDATION_WITH_FAILED_META_BASELINE_GATE", "detail": "Meta-baseline-gate did not pass; do not present final item/move/spread recommendations.", "gate_failures": gate.get("failures", [])[:10]})

    if LOCAL_FIT_RE.search(text):
        if not gate or gate.get("status") != "pass":
            failures.append({"code": "FAIL_ITEMTHREATFIT_USED_AS_META_BASELINE", "detail": "Local itemthreatfit/item-clause/local fit wording cannot be used as final recommendation evidence without passed meta-baseline-gate."})
        else:
            warnings.append({"code": "WARN_LOCAL_FIT_WORDING_REQUIRES_CLEAR_LABEL", "detail": "If local fit is mentioned, label it as fallback/override and include the meta diff/search basis."})

    return {
        "mode": "recommendation_provenance_lint",
        "engine_version": RECOMMENDATION_LINT_VERSION,
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "warnings": warnings,
        "has_meta_baseline_gate": bool(gate),
        "rule": "Public actionable item/move/spread recommendations require a passed meta-baseline-gate; local fit/itemthreatfit/item-clause repair alone is not recommendation evidence.",
    }
