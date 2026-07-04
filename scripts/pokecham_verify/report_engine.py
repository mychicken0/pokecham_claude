"""v29.45 structured battle report renderer.

This renderer is intentionally simple: it converts a structured report JSON into
human-readable Markdown. It does not parse raw battle logs or invent mechanics.
"""
from __future__ import annotations

from typing import Any

REPORT_ENGINE_VERSION = "v29.45-readable-battle-report-output"


def _as_list(x: Any) -> list:
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _bullet_lines(items: Any) -> list[str]:
    out = []
    for item in _as_list(items):
        if isinstance(item, dict):
            label = item.get("label") or item.get("title") or item.get("turn") or "item"
            detail = item.get("detail") or item.get("why") or item.get("text") or item.get("event") or ""
            out.append(f"- **{label}:** {detail}" if detail else f"- {label}")
        else:
            out.append(f"- {item}")
    return out


def _table(rows: list[dict], columns: list[str]) -> list[str]:
    if not rows or not columns:
        return []
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join(["---"] * len(columns)) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in columns) + " |")
    return lines


def render_battle_report(report_payload: dict, style: str = "standard") -> str:
    if not isinstance(report_payload, dict):
        return "# Battle Report\n\nInvalid report payload: expected JSON object."
    title = report_payload.get("title") or report_payload.get("match") or "Battle Report"
    winner = report_payload.get("winner", "")
    main_reason = report_payload.get("main_reason", "")
    biggest_mistake = report_payload.get("biggest_mistake", "")
    lines: list[str] = [f"# {title}", "", "## 1. Verdict"]
    if winner:
        lines.append(f"- **Winner:** {winner}")
    if main_reason:
        lines.append(f"- **Main reason:** {main_reason}")
    if biggest_mistake:
        lines.append(f"- **Biggest mistake:** {biggest_mistake}")

    mistakes = _as_list(report_payload.get("key_mistakes"))
    if mistakes:
        lines += ["", "## 2. Key mistakes"] + _bullet_lines(mistakes)

    turns = _as_list(report_payload.get("turning_points") or report_payload.get("turns"))
    if turns:
        lines += ["", "## 3. Key turning points"]
        if all(isinstance(t, dict) for t in turns):
            lines += _table(turns, ["turn", "event", "why"])
        else:
            lines += _bullet_lines(turns)

    matrix = report_payload.get("verified_matrix") or report_payload.get("switch_table")
    if matrix:
        lines += ["", "## 4. Verified switch/type table"]
        direction = matrix.get("direction_display") or matrix.get("direction") or "ENEMY LIKELY MOVE → OUR SWITCH-IN"
        cell_semantics = matrix.get("cell_semantics") or "x taken"
        lines.append(f"Direction: **{direction}**")
        lines.append(f"Cell: **{cell_semantics}**")
        rows = _as_list(matrix.get("rows"))
        cols = matrix.get("columns") or []
        if rows and cols:
            lines += [""] + _table(rows, cols)
        elif isinstance(matrix.get("markdown"), str):
            lines += ["", matrix["markdown"]]

    build = _as_list(report_payload.get("build_issues"))
    if build:
        lines += ["", "## 5. Team/build issues"]
        if all(isinstance(x, dict) for x in build):
            lines += _table(build, ["pokemon", "issue", "impact"])
        else:
            lines += _bullet_lines(build)

    score = report_payload.get("score")
    if score:
        lines += ["", "## 6. Score"]
        if isinstance(score, list):
            lines += _table(score, ["side", "lead", "positioning", "build", "endgame", "overall", "reason"])
        else:
            lines += _bullet_lines(score)

    summary = report_payload.get("summary") or report_payload.get("final_summary")
    if summary:
        lines += ["", "## 7. Final summary", str(summary)]
    return "\n".join(lines).rstrip() + "\n"


def battle_report_template(style: str = "standard") -> dict:
    return {
        "mode": "battle_report_template",
        "engine_version": REPORT_ENGINE_VERSION,
        "style": style,
        "required_sections": [
            "Verdict",
            "Key mistakes",
            "Key turning points / turn references",
            "Verified switch/type table when making switch/type advice",
            "Build issues if team sheet is supplied",
            "Score with reasons if scoring is used",
            "Final summary",
        ],
        "receipt_requirements": {
            "switch_advice": ["SWITCH_SAFETY_MATRIX", "INCOMING_DEFENSE_MATRIX"],
            "offensive_coverage": ["OUTGOING_ATTACK_MATRIX", "typechart", "complete damage receipt"],
            "ko_survival": ["complete damage receipt"],
        },
        "rule": "Use this template for readable battle-log analysis. Do not dump raw receipt JSON; summarize verified rows with explicit direction and taken/dealt cells.",
    }
