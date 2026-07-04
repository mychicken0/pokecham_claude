"""v29.45 readable battle report lint.

This is an output-layer guard for battle-log analysis reports. It does not add
new game mechanics. It checks that the public report is readable, sectioned, and
still gated by v29.44 action matrices for switch/type advice.
"""
from __future__ import annotations

import re
from typing import Any

from . import legacy

REPORT_ENGINE_VERSION = "v29.45-readable-battle-report-output"

STYLE_WORD_LIMITS = {
    "compact": 900,
    "standard": 2400,
    "deep": 5200,
}

VERDICT_RE = re.compile(r"(?i)(\bverdict\b|ผล\s*:?|สรุป(?:สั้น|สุดท้าย)?|winner|ผู้ชนะ)")
KEY_MISTAKE_RE = re.compile(r"(?i)(key\s*mistakes?|biggest\s*mistake|ใครผิด|จุดผิด|ความผิด|พลาด|turning\s*points?|จุดเปลี่ยน)")
TURN_REF_RE = re.compile(r"(?i)(\bturn\s*\d+\b|เทิร์น\s*\d+|T\s*\d+|T\d+)" )
RAW_RECEIPT_RE = re.compile(r"(?i)(\"matrix_kind\"\s*:|\"damage_completeness\"\s*:|\"public_ko_claim_allowed\"\s*:|\"receipt_counts\"\s*:|\"typechart_receipts_found\"\s*:)")
JSON_FENCE_RE = re.compile(r"```\s*json[\s\S]*?```", re.I)
DIRECTION_LINE_RE = re.compile(r"(?i)(ENEMY\s+(?:MOVE\s+TYPE|LIKELY\s+MOVE)\s*(?:→|->)\s*OUR\s+(?:DEFENDER|SWITCH[-\s]*IN)|OUR\s+MOVE\s*(?:→|->)\s*ENEMY\s+DEFENDER)")
MATRIX_MENTION_RE = re.compile(r"(?i)(INCOMING_DEFENSE_MATRIX|OUTGOING_ATTACK_MATRIX|SWITCH_SAFETY_MATRIX|incoming defense matrix|outgoing attack matrix|switch safety matrix)")
SWITCH_ADVICE_RE = re.compile(r"(?i)(\bswap\b|\bswitch\b|\bpivot\b|safe\s*switch|switch\s*in|สลับ|เปลี่ยน|ส่ง.+เข้า|ควร.+(?:เข้า|รับ)|รับ(?:ดาเมจ|ท่า)?|ต้าน)")
TYPE_TABLE_RE = re.compile(r"(?i)(Fire|Water|Electric|Grass|Ice|Fighting|Poison|Ground|Flying|Psychic|Bug|Rock|Ghost|Dragon|Dark|Steel|Fairy).*(0\s*x|0\.5\s*x|1\s*x|2\s*x|4\s*x|neutral|resisted|immune|super[_\s-]*effective)")
TYPE_HEADER_RE = re.compile(r"(?i)\|[^\n]*(Fire|Water|Electric|Grass|Ice|Fighting|Poison|Ground|Flying|Psychic|Bug|Rock|Ghost|Dragon|Dark|Steel|Fairy)[^\n]*\|[^\n]*(Fire|Water|Electric|Grass|Ice|Fighting|Poison|Ground|Flying|Psychic|Bug|Rock|Ghost|Dragon|Dark|Steel|Fairy)[^\n]*\|")
MULTIPLIER_ROW_RE = re.compile(r"(?i)\|[^\n]*(0\s*x|0\.5\s*x|1\s*x|2\s*x|4\s*x|neutral|resisted|immune|super[_\s-]*effective)[^\n]*\|")
CONCRETE_KO_RE = re.compile(r"(?i)(\bOHKO\b|\b2HKO\b|guaranteed|การันตี|survives?|live\b|ไม่ตาย|รอด(?:\s*1)?|ตายทุก|KO\s*chance)")
OBSERVED_LOG_DAMAGE_RE = re.compile(r"(?i)(lost\s+\d+(?:\.\d+)?%|เสีย\s*\d+(?:\.\d+)?%|โดน\s*\d+(?:\.\d+)?%|ผลจริง|จาก\s*log|observed|battle\s*log)")
SCORE_RE = re.compile(r"(?:\b\d+(?:\.\d+)?\s*/\s*10\b|คะแนน)")
REASON_RE = re.compile(r"(?i)(reason|why|because|เพราะ|เหตุผล|impact|ผล|เนื่องจาก|สาเหตุ)")


def _word_count(text: str) -> int:
    # Thai has no spaces; this is only a rough verbosity guard. Count ASCII-ish
    # word chunks plus Thai sentence chunks.
    chunks = re.findall(r"[A-Za-z0-9_./+-]+|[\u0E00-\u0E7F]+", text or "")
    return len(chunks)


def _matrix_kinds(receipt: dict) -> set[str]:
    kinds, _ = legacy._collect_matrix_kinds_from_receipt(receipt or {})
    return set(kinds)


def _has_complete_damage_receipt(receipt: dict) -> bool:
    for d in legacy._collect_damage_receipts(receipt or {}):
        if d.get("damage_completeness") == "complete" and d.get("public_ko_claim_allowed") is True:
            return True
    return False


def _line_neighborhood(lines: list[str], idx: int, radius: int = 2) -> str:
    lo = max(0, idx - radius)
    hi = min(len(lines), idx + radius + 1)
    return "\n".join(lines[lo:hi])


def battle_report_lint(answer_text: str, receipt: dict | None = None, style: str = "standard") -> dict:
    receipt = receipt or {}
    style = (style or "standard").lower()
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    text = str(answer_text or "")
    lines = text.splitlines()
    kinds = _matrix_kinds(receipt)
    has_switch_or_incoming = bool(kinds.intersection({"SWITCH_SAFETY_MATRIX", "INCOMING_DEFENSE_MATRIX"}))
    has_outgoing = "OUTGOING_ATTACK_MATRIX" in kinds

    if not VERDICT_RE.search(text[:1200]):
        failures.append({"code": "FAIL_BATTLE_REPORT_MISSING_VERDICT", "detail": "Battle reports must start with a verdict/winner/main reason section."})
    if not KEY_MISTAKE_RE.search(text):
        failures.append({"code": "FAIL_BATTLE_REPORT_MISSING_KEY_MISTAKES", "detail": "Battle reports must identify key mistakes/turning points, not only narrate the log."})
    if not TURN_REF_RE.search(text):
        failures.append({"code": "FAIL_BATTLE_REPORT_MISSING_TURN_REFERENCES", "detail": "Battle reports should cite key turns such as Turn 1/Turn 2 so the reader can map claims to the log."})

    if RAW_RECEIPT_RE.search(text):
        failures.append({"code": "FAIL_BATTLE_REPORT_DUMPS_RAW_RECEIPT_JSON", "detail": "Summarize receipts in human tables; do not dump raw verifier JSON in public battle reports."})
    for fence in JSON_FENCE_RE.findall(text):
        if RAW_RECEIPT_RE.search(fence) or len(fence.splitlines()) > 8:
            failures.append({"code": "FAIL_BATTLE_REPORT_DUMPS_RAW_RECEIPT_JSON", "detail": "Long JSON fences/raw receipts belong in debug artifacts, not the user-readable report."})
            break

    limit = STYLE_WORD_LIMITS.get(style, STYLE_WORD_LIMITS["standard"])
    wc = _word_count(text)
    if wc > limit:
        failures.append({"code": "FAIL_BATTLE_REPORT_TOO_LONG_FOR_STYLE", "style": style, "word_count_approx": wc, "limit": limit, "detail": "Use compact/standard/deep intentionally; do not over-report beyond the requested style."})

    # Matrix/action gates specific to reports. This overlaps v29.44 but keeps
    # report-specific wording and observed-log damage exceptions.
    switch_lines = []
    type_table_lines = []
    for i, line in enumerate(lines, start=1):
        if SWITCH_ADVICE_RE.search(line) and not legacy._is_caveat_or_audit_line(line):
            switch_lines.append({"line": i, "text": line.strip()[:260]})
        if TYPE_TABLE_RE.search(line) and not legacy._is_caveat_or_audit_line(line):
            type_table_lines.append({"line": i, "text": line.strip()[:260]})
    if switch_lines and not has_switch_or_incoming:
        failures.append({"code": "FAIL_BATTLE_REPORT_SWITCH_ADVICE_WITHOUT_MATRIX", "detail": "Switch/swap/pivot advice in a battle report requires SWITCH_SAFETY_MATRIX or INCOMING_DEFENSE_MATRIX receipt.", "claim_lines": switch_lines[:8]})
    has_type_header_table = bool(TYPE_HEADER_RE.search(text) and MULTIPLIER_ROW_RE.search(text))
    if (MATRIX_MENTION_RE.search(text) or type_table_lines or has_type_header_table) and not DIRECTION_LINE_RE.search(text):
        failures.append({"code": "FAIL_BATTLE_REPORT_TYPE_TABLE_MISSING_DIRECTION", "detail": "Type/switch tables in reports must include a direction line such as ENEMY LIKELY MOVE → OUR SWITCH-IN or OUR MOVE → ENEMY DEFENDER.", "lines": type_table_lines[:8]})
    if re.search(r"(?i)(coverage|ตี(?:แรง|เข้า|ใส่)|OUR\s+MOVE|OUTGOING_ATTACK_MATRIX|super\s*effective)", text) and not (has_outgoing or has_switch_or_incoming or legacy._collect_typechart_receipts(receipt)):
        warnings.append({"code": "WARN_BATTLE_REPORT_OFFENSIVE_COVERAGE_WITHOUT_OUTGOING_MATRIX", "detail": "Offensive coverage sections should use OUTGOING_ATTACK_MATRIX, direct typechart receipts, or damage receipts."})

    # Concrete KO/survival claims still require complete damage receipts. Observed
    # battle-log percentages are allowed if phrased as observed/log damage.
    if CONCRETE_KO_RE.search(text) and not _has_complete_damage_receipt(receipt):
        failures.append({"code": "FAIL_BATTLE_REPORT_DAMAGE_CLAIM_WITHOUT_COMPLETE_DAMAGE_RECEIPT", "detail": "OHKO/2HKO/guaranteed/survival claims require complete damage receipts. Observed log percentages may be quoted as observed damage only."})
    for i, line in enumerate(lines):
        if re.search(r"\d+(?:\.\d+)?%", line) and not OBSERVED_LOG_DAMAGE_RE.search(_line_neighborhood(lines, i, 1)):
            warnings.append({"code": "WARN_PERCENT_DAMAGE_NOT_MARKED_OBSERVED", "line": i + 1, "detail": "Percent damage in reports should be clearly marked as observed from the battle log unless backed by a complete damage receipt.", "text": line.strip()[:220]})
            break

    # Scores need a reason nearby.
    score_lines = []
    for i, line in enumerate(lines):
        if SCORE_RE.search(line):
            if not REASON_RE.search(_line_neighborhood(lines, i, 2)):
                score_lines.append({"line": i + 1, "text": line.strip()[:260]})
    if score_lines:
        failures.append({"code": "FAIL_BATTLE_REPORT_SCORE_WITHOUT_REASON", "detail": "Scores must include reasons nearby; avoid unsupported numeric ratings.", "lines": score_lines[:8]})

    return {
        "mode": "battle_report_lint",
        "engine_version": REPORT_ENGINE_VERSION,
        "style": style,
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "warnings": warnings,
        "matrix_kinds_found": sorted(kinds),
        "word_count_approx": wc,
        "rule": "Readable battle reports must start with a verdict, identify key mistakes/turns, summarize receipts without dumping raw JSON, use direction-explicit matrix tables for switch/type advice, and reserve KO/survival claims for complete damage receipts.",
    }
