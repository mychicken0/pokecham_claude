#!/usr/bin/env python3
"""
PokeCham verification engine.

Implements the lookup/receipt functions required by
references/04_verification_harness_spec.md section 10 and team-level gates.

This performs REAL pandas lookups against the bundled data/ CSVs.
It never fabricates a "pass" — every receipt is the direct result of
a row lookup against the local files. No receipt = no pass.

CLI usage (one entity per call, JSON receipt on stdout):

    python verify.py pokemon <name_or_id>
    python verify.py item <name_or_id>
    python verify.py ability <pokemon_name_or_id> <ability_name>
    python verify.py move <pokemon_name_or_id> <move_name>
    python verify.py set <path_to_set.json>      # one Pokémon set object
    python verify.py team <path_to_team.json>    # full six-Pokémon team object/list + team-level gates
    python verify.py strict_mb <name_or_id>       # strict M-B status check
    python verify.py spread <json_or_text>        # 0-32 per stat, total 66/66 gate
    python verify.py mechanic <mechanic_or_move>   # priority/mechanic receipt, e.g. Trick Room
    python verify.py priority <pokemon> <move> [ability]  # effective priority receipt incl. Prankster
    python verify.py typechart <attacking_type> <defender_pokemon_or_type_pair>  # dual-type effectiveness receipt
    python verify.py typepassive <scenario_json_or_path>  # type passive/status/weather/hazard property receipt
    python verify.py typepassive-regression-tests # locked type-passive property regression cases
    python verify.py type-regression-tests     # locked typechart regression cases
    python verify.py active-form <slot_or_scenario_json>  # active form / battle stat source receipt
    python verify.py stat <pokemon> <nature> <spread_json_or_text> [state_json]  # final displayed stat receipt via active-form resolver
    python verify.py damage <scenario_json_or_path>  # board-aware 16-roll damage receipt
    python verify.py sequence <scenario_json_or_path>  # stateful multi-hit / on-hit ability sequence receipt
    python verify.py teamfit <path_to_team.json>   # team-fit / provenance gate receipt
    python verify.py interaction <scenario_json_or_path>  # mechanic relationship receipt, e.g. Prankster Taunt vs Armor Tail
    python verify.py threatfit <team.json> [meta_threats.json]  # meta threat -> team answer matrix
    python verify.py spreadfit <team.json> [meta_spreads.json]  # meta-spread baseline / override benchmark gate
    python verify.py itemspread <team.json>  # item-spread coherence / reason receipt gate
    python verify.py boardscan <scenario_json_or_path>  # board-level move-target/ally interaction receipt
    python verify.py counterroute <scenario_json_or_path>  # counter/check route receipt for threat rankings
    python verify.py selfaudit <answer.md> <receipt.json>  # bounded final claim audit/lint pass
    python verify.py ascii-assets              # Pokémon ASCII asset bundle status
    python verify.py render <path_to_team.json>    # default compact public-render draft; optional --platform claude --style claude-html-card or --style inline-ascii-card
    python verify.py lint-output <answer.md> <team_receipt.json>  # public-output render lint

All functions are also importable for ad-hoc / batch use:

    from verify import verify_pokemon, verify_item, verify_move_on_pokemon, \
        verify_ability_on_pokemon, verify_set, verify_team, verify_mechanic, verify_priority_on_pokemon, verify_type_effectiveness, verify_typepassive, verify_active_form, verify_stat, verify_damage, verify_sequence, verify_teamfit, verify_interaction, verify_boardscan, verify_counterroute, verify_threatfit, verify_spreadfit, verify_itemspread, verify_threataudit, verify_itemthreatfit, ascii_assets_status, render_team_markdown, lint_public_output, verify_final_self_audit
"""

import sys
import os
import re
import json
import math
import html
import pandas as pd

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
ASCII_ASSET_BUNDLE = os.path.join(ASSETS_DIR, "champions_ascii", "ascii_bundle.json")

POKEMON_CSV = os.path.join(DATA_DIR, "01_ranked_champions_pokemon_core.csv")
MOVE_CSVS = [
    os.path.join(DATA_DIR, "05_pokemon_moves_part1.csv"),
    os.path.join(DATA_DIR, "06_pokemon_moves_part2.csv"),
    os.path.join(DATA_DIR, "07_pokemon_moves_part3.csv"),
]
GLOBAL_CSV = os.path.join(DATA_DIR, "08_global_moves_abilities_items.csv")
TYPE_PASSIVE_CSV = os.path.join(DATA_DIR, "09_type_passive_properties.csv")

_pokemon_df = None
_moves_df = None
_global_df = None
_type_passive_df = None
_ascii_bundle_cache = None


def normalize_id(name: str) -> str:
    """Lowercase, strip non-alphanumerics. Mirrors the `id` column convention
    used in the data files (e.g. 'Kowtow Cleave' -> 'kowtowcleave')."""
    if name is None:
        return ""
    return re.sub(r"[^a-z0-9]", "", name.strip().lower())


def load_01_pokemon() -> pd.DataFrame:
    global _pokemon_df
    if _pokemon_df is None:
        _pokemon_df = pd.read_csv(POKEMON_CSV, dtype=str).fillna("")
        _pokemon_df["_norm_id"] = _pokemon_df["id"].apply(normalize_id)
        _pokemon_df["_norm_name"] = _pokemon_df["name"].apply(normalize_id)
    return _pokemon_df


def load_05_07_moves() -> pd.DataFrame:
    global _moves_df
    if _moves_df is None:
        frames = [pd.read_csv(p, dtype=str).fillna("") for p in MOVE_CSVS]
        df = pd.concat(frames, ignore_index=True)
        df["_norm_pokemon_id"] = df["pokemon_id"].apply(normalize_id)
        df["_norm_pokemon_name"] = df["pokemon_name"].apply(normalize_id)
        df["_norm_move_id"] = df["move_id"].apply(normalize_id)
        df["_norm_move_name"] = df["move_name"].apply(normalize_id)
        _moves_df = df
    return _moves_df


def load_08_global() -> pd.DataFrame:
    global _global_df
    if _global_df is None:
        df = pd.read_csv(GLOBAL_CSV, dtype=str).fillna("")
        df["_norm_id"] = df["id"].apply(normalize_id)
        df["_norm_name"] = df["name"].apply(normalize_id)
        _global_df = df
    return _global_df


def load_09_type_passive_properties() -> pd.DataFrame:
    """Load curated type passive/status/weather/hazard rules.

    This file is intentionally separate from the attacking type chart. It covers
    passive properties such as Dark vs Prankster status, Rock in sand, grounded
    hazard immunity, and type status immunities. A public claim about these
    properties requires a receipt from verify.py typepassive, boardscan, or a
    derived receipt that includes typepassive_receipt.
    """
    global _type_passive_df
    if _type_passive_df is None:
        if not os.path.exists(TYPE_PASSIVE_CSV):
            _type_passive_df = pd.DataFrame(columns=[
                "rule_id", "defender_type", "trigger_kind", "trigger_name",
                "condition", "result", "exception", "source_status",
                "source_note", "public_label"
            ])
        else:
            _type_passive_df = pd.read_csv(TYPE_PASSIVE_CSV, dtype=str).fillna("")
            _type_passive_df["_norm_type"] = _type_passive_df["defender_type"].apply(normalize_id)
            _type_passive_df["_norm_trigger"] = _type_passive_df["trigger_name"].apply(normalize_id)
            _type_passive_df["_norm_kind"] = _type_passive_df["trigger_kind"].apply(normalize_id)
    return _type_passive_df


def _find_pokemon_row(pokemon_name_or_id: str):
    df = load_01_pokemon()
    key = normalize_id(pokemon_name_or_id)
    match = df[(df["_norm_id"] == key) | (df["_norm_name"] == key)]
    if match.empty:
        return None
    return match.iloc[0]




def _load_ascii_bundle() -> dict:
    """Load bundled Pokémon ASCII assets from a single JSON file.

    v29.31 keeps Pokémon ASCII for optional card views only. Item ASCII was removed
    because it hurt readability. ASCII art is a readability aid only; legality
    and mechanics still come from receipts.
    """
    global _ascii_bundle_cache
    if _ascii_bundle_cache is not None:
        return _ascii_bundle_cache
    if not os.path.exists(ASCII_ASSET_BUNDLE):
        _ascii_bundle_cache = {"pokemon": {}, "items": {}, "status": "n/a"}
        return _ascii_bundle_cache
    with open(ASCII_ASSET_BUNDLE, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("pokemon", {})
    data.setdefault("items", {})
    _ascii_bundle_cache = data
    return data


def _ascii_lookup_candidates(entity_id: str, display_name: str = "") -> list:
    """Return robust ASCII bundle lookup ids.

    The bundle is keyed by local Pokémon ids such as `sinistcha`, but card
    renderers sometimes receive display names (`Tyranitar → Mega Tyranitar`,
    `Mega Swampert`, or localized/pretty strings). Do not invent art; only
    try deterministic local-id/display-name aliases and use a real bundled
    entry if present.
    """
    raw = [entity_id or "", display_name or ""]
    out = []
    for val in raw:
        if not val:
            continue
        # Split active-form display like "Tyranitar → Mega Tyranitar" and try both sides.
        pieces = [val]
        for sep in ["→", "->", "/", "|"]:
            if sep in val:
                pieces.extend([x.strip() for x in val.split(sep) if x.strip()])
        for x in pieces:
            nid = normalize_id(x)
            if nid and nid not in out:
                out.append(nid)
            # Common display form aliases: "Mega Swampert" -> swampertmega.
            if nid.startswith("mega") and len(nid) > 4:
                alias = nid[4:] + "mega"
                if alias not in out:
                    out.append(alias)
            if nid.endswith("mega") and len(nid) > 4:
                base = nid[:-4]
                if base not in out:
                    out.append(base)
    return out

def _ascii_asset(kind: str, entity_id: str, display_name: str = "") -> dict:
    bundle = _load_ascii_bundle()
    bucket = "pokemon" if normalize_id(kind) == "pokemon" else "items"
    assets = bundle.get(bucket, {}) or {}
    candidates = _ascii_lookup_candidates(entity_id, display_name)
    for eid in candidates:
        text = assets.get(eid, "")
        if text:
            return {
                "kind": bucket,
                "id": eid,
                "requested_id": normalize_id(entity_id),
                "name": display_name or entity_id,
                "status": "pass",
                "text": text,
                "source": "assets/champions_ascii/ascii_bundle.json",
                "rule": "Pokémon ASCII art is an inline readability aid only; receipts/text labels remain source of truth.",
            }
    return {
        "kind": bucket,
        "id": normalize_id(entity_id),
        "lookup_candidates": candidates,
        "name": display_name or entity_id,
        "status": "missing",
        "source": "assets/champions_ascii/ascii_bundle.json",
        "reason": "no matching Pokémon ASCII asset id in bundle, or item ASCII is intentionally disabled; text labels remain source of truth",
    }


def _image_asset(kind: str, entity_id: str, display_name: str = "", width: int = 48) -> dict:
    """Compatibility stub: image assets are omitted; v29.31 uses platform-aware optional card views instead."""
    return {
        "kind": "pokemon" if kind == "pokemon" else "items",
        "id": normalize_id(entity_id),
        "name": display_name or entity_id,
        "status": "replaced_by_ascii",
        "ascii_asset": _ascii_asset(kind, entity_id, display_name),
        "reason": "v29.38 uses platform-aware optional Pokémon card views; Claude HTML cards must go through the platform HTML/widget renderer and item ASCII stays disabled",
    }


def ascii_assets_status() -> dict:
    bundle = _load_ascii_bundle()
    pokemon_count = len(bundle.get("pokemon", {}) or {})
    item_count = len(bundle.get("items", {}) or {})
    status = "pass" if pokemon_count else "n/a"
    return {
        "mode": "ascii_assets_status",
        "status": status,
        "asset_packaging": "single_ascii_bundle_json",
        "bundle_path": "assets/champions_ascii/ascii_bundle.json",
        "pokemon_ascii": pokemon_count,
        "item_ascii": item_count,
        "item_ascii_policy": "disabled_intentionally",
        "default_render_style": "compact_text_no_cards",
        "optional_card_styles": ["claude-html-card", "inline-ascii-card", "markdown-ascii-card"],
        "platform_policy": "Claude may offer/use HTML cards only through the platform HTML/widget/artifact renderer; non-Claude or uncertain platforms must offer/use inline Markdown ASCII cards only.",
        "rule": "Default full-team answers are compact/no-card. Offer one platform-appropriate card view after final output. In Claude use --platform claude and --style claude-html-card on request and show it through the platform widget/artifact renderer; outside Claude use --style inline-ascii-card/markdown-ascii-card only and print inline in chat. Never use card art as legality evidence.",
    }


def image_assets_status() -> dict:
    status = ascii_assets_status()
    return {
        "mode": "image_assets_status",
        "status": "replaced_by_ascii" if status.get("status") == "pass" else "n/a",
        "asset_packaging": status.get("asset_packaging"),
        "pokemon_images": 0,
        "item_images": 0,
        "ascii_assets": status,
        "rule": "Image assets are intentionally omitted; v29.38 can display platform-aware optional card views; Claude HTML cards use only the canonical template and should be shown via widget/artifact, never raw chat HTML.",
    }

def verify_pokemon(pokemon_name_or_id: str) -> dict:
    row = _find_pokemon_row(pokemon_name_or_id)
    if row is None:
        return {
            "entity": "pokemon",
            "query": pokemon_name_or_id,
            "id": normalize_id(pokemon_name_or_id),
            "source": "01",
            "status": "fail",
            "reason": "no exact row match in 01_ranked_champions_pokemon_core.csv",
        }
    return {
        "entity": "pokemon",
        "query": pokemon_name_or_id,
        "id": row["id"],
        "name": row["name"],
        "types": row["types"],
        "stats": {k: row[k] for k in ["hp", "atk", "def", "spa", "spd", "spe"]},
        "abilities": [a.strip() for a in row["abilities"].split(";")],
        "ranked_default_status": row["ranked_default_status"],
        "strict_M_B_status": row["strict_M_B_status"],
        "current_format_status": row["current_format_status"],
        "image_asset": _image_asset("pokemon", row["id"], row["name"], width=64),
        "ascii_asset": _ascii_asset("pokemon", row["id"], row["name"]),
        "source": "01",
        "status": "pass",
    }


def verify_strict_mb(pokemon_name_or_id: str) -> dict:
    row = _find_pokemon_row(pokemon_name_or_id)
    if row is None:
        return {
            "entity": "strict_mb_status",
            "query": pokemon_name_or_id,
            "source": "01",
            "status": "fail",
            "reason": "pokemon not found in 01",
        }
    is_confirmed = row["strict_M_B_status"].strip().lower() == "confirmed"
    return {
        "entity": "strict_mb_status",
        "query": pokemon_name_or_id,
        "id": row["id"],
        "strict_M_B_status": row["strict_M_B_status"],
        "current_format_status": row["current_format_status"],
        "strict_mb_legal": is_confirmed,
        "source": "01",
        "status": "pass",
    }


def verify_ability_on_pokemon(pokemon_name_or_id: str, ability_name: str) -> dict:
    row = _find_pokemon_row(pokemon_name_or_id)
    if row is None:
        return {
            "entity": "ability",
            "pokemon_query": pokemon_name_or_id,
            "ability_query": ability_name,
            "source": "01",
            "status": "fail",
            "reason": "pokemon not found in 01",
        }
    abilities = [a.strip() for a in row["abilities"].split(";")]
    abilities_norm = [normalize_id(a) for a in abilities]
    key = normalize_id(ability_name)
    if key not in abilities_norm:
        return {
            "entity": "ability",
            "pokemon_id": row["id"],
            "ability_query": ability_name,
            "available_abilities": abilities,
            "source": "01",
            "status": "fail",
            "reason": "ability not listed for this pokemon in 01",
        }
    matched = abilities[abilities_norm.index(key)]
    return {
        "entity": "ability",
        "pokemon_id": row["id"],
        "ability_name": matched,
        "ability_id": key,
        "source": "01",
        "status": "pass",
    }


def verify_item(item_name_or_id: str) -> dict:
    df = load_08_global()
    key = normalize_id(item_name_or_id)
    items = df[df["entity_type"].str.lower() == "item"]
    match = items[(items["_norm_id"] == key) | (items["_norm_name"] == key)]
    if match.empty:
        wrong_type_match = df[(df["_norm_id"] == key) | (df["_norm_name"] == key)]
        wrong_type_rows = []
        if not wrong_type_match.empty:
            wrong_type_rows = wrong_type_match[["entity_type", "id", "name", "source_status"]].to_dict("records")
        return {
            "entity": "item",
            "query": item_name_or_id,
            "id": key,
            "entity_type_expected": "item",
            "matched_rows": 0,
            "wrong_entity_type_matches": wrong_type_rows,
            "source": "08",
            "status": "fail",
            "reason": "no exact item row in 08_global_moves_abilities_items.csv; wrong entity_type or similar-name matches are not an item pass",
        }
    row = match.iloc[0]
    return {
        "entity": "item",
        "query": item_name_or_id,
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "source_status": row.get("source_status", ""),
        "extra": row.get("extra", ""),
        "entity_type_expected": "item",
        "matched_rows": int(len(match)),
        "image_asset": _image_asset("item", row["id"], row["name"], width=28),
        "ascii_asset": _ascii_asset("item", row["id"], row["name"]),
        "source": "08",
        "status": "pass",
    }


def verify_move_on_pokemon(pokemon_name_or_id: str, move_name_or_id: str) -> dict:
    df = load_05_07_moves()
    pkey = normalize_id(pokemon_name_or_id)
    mkey = normalize_id(move_name_or_id)
    match = df[
        ((df["_norm_pokemon_id"] == pkey) | (df["_norm_pokemon_name"] == pkey))
        & ((df["_norm_move_id"] == mkey) | (df["_norm_move_name"] == mkey))
    ]
    if match.empty:
        return {
            "entity": "move",
            "pokemon_query": pokemon_name_or_id,
            "move_query": move_name_or_id,
            "source": "05-07",
            "status": "fail",
            "reason": "no exact pokemon+move row across 05_pokemon_moves_part1/2/3.csv",
        }
    row = match.iloc[0]
    type_emoji = {
        "normal": "⚪", "fire": "🔥", "water": "💧", "electric": "⚡",
        "grass": "🌿", "ice": "🧊", "fighting": "🤜", "poison": "☠️",
        "ground": "🟤", "flying": "🪽", "psychic": "🔮", "bug": "🐞",
        "rock": "🪨", "ghost": "👻", "dragon": "🐉", "dark": "🌑",
        "steel": "⚙️", "fairy": "🧚",
    }
    emoji = type_emoji.get(row["type"].strip().lower(), "")
    return {
        "entity": "move",
        "pokemon_id": row["pokemon_id"],
        "move_id": row["move_id"],
        "move_name": row["move_name"],
        "type": row["type"],
        "emoji": emoji,
        "display": f"{emoji} {row['move_name']}" if emoji else row["move_name"],
        "category": row["category"],
        "power": row["power"],
        "accuracy": row["accuracy"],
        "source": "05-07",
        "status": "pass",
    }


# ---------------------------------------------------------------------------
# Active form / battle-state resolver
# ---------------------------------------------------------------------------
# The selected team form is not always the battle stat source. Mega Evolution,
# Palafin-style state changes, and stance/form mechanics can change the active
# row whose base stats, typing, and battle ability should be used for stat,
# damage, speed, priority, typechart, and public rendering receipts.

FORM_STATE_REQUIRED_IDS = {
    "palafinhero": "Zero to Hero requires state.has_switched_out=true and local active-form row must exist",
    "aegislashblade": "Stance Change requires state.stance=blade / state.form=blade",
    "aegislashshield": "Stance Change requires state.stance=shield / state.form=shield",
}


def _row_to_pokemon_receipt(row) -> dict:
    return {
        "entity": "pokemon",
        "query": row.get("id", ""),
        "id": row["id"],
        "name": row["name"],
        "types": row["types"],
        "stats": {k: row[k] for k in ["hp", "atk", "def", "spa", "spd", "spe"]},
        "abilities": [a.strip() for a in row["abilities"].split(";") if a.strip()],
        "ranked_default_status": row.get("ranked_default_status", ""),
        "strict_M_B_status": row.get("strict_M_B_status", ""),
        "current_format_status": row.get("current_format_status", ""),
        "image_asset": _image_asset("pokemon", row["id"], row["name"], width=64),
        "ascii_asset": _ascii_asset("pokemon", row["id"], row["name"]),
        "source": "01",
        "status": "pass",
    }


def _is_mega_item_receipt(item_receipt: dict) -> bool:
    if not item_receipt or item_receipt.get("status") != "pass":
        return False
    return "mega-evolution" in normalize_id(item_receipt.get("extra", "")) or "megastone" in normalize_id(item_receipt.get("description", ""))


def _mega_base_name_from_item(item_receipt: dict) -> str:
    desc = item_receipt.get("description", "") or ""
    # Local mega stone descriptions use: "... A Gallade holding this stone ...".
    # Use the LAST such match so the leading "One of A variety" text is ignored.
    matches = re.findall(r"(?:^|[.!?]\s*)A\s+(.+?)\s+holding\s+this\s+stone", desc, flags=re.I)
    if matches:
        return matches[-1].strip()
    name = item_receipt.get("name", "") or item_receipt.get("id", "")
    # Fallback: remove common mega-stone suffixes.
    name = re.sub(r"ite\s+[XY]$", "", name, flags=re.I)
    name = re.sub(r"ite$", "", name, flags=re.I)
    return name.strip()


def _resolve_mega_form_from_item(base_row, item_receipt: dict) -> dict:
    base_id = base_row["id"]
    base_name = base_row["name"]
    item_id = normalize_id(item_receipt.get("id", ""))
    item_name_norm = normalize_id(item_receipt.get("name", ""))
    df = load_01_pokemon()
    base_from_item = _mega_base_name_from_item(item_receipt)
    base_from_item_norm = normalize_id(base_from_item)
    if base_from_item_norm and base_from_item_norm not in {normalize_id(base_name), normalize_id(base_id)}:
        return {
            "status": "fail",
            "code": "FAIL_MEGA_ITEM_FORM_MISMATCH",
            "reason": f"Mega Stone description targets {base_from_item}, not {base_name}",
            "base_pokemon": base_id,
            "item": item_receipt.get("name", item_id),
        }

    candidates = df[df["name"].str.lower().str.startswith("mega ", na=False)]
    # Prefer exact ID patterns.
    preferred_ids = []
    if item_id.endswith("itex") or item_name_norm.endswith("x"):
        preferred_ids.append(base_id + "megax")
    if item_id.endswith("itey") or item_name_norm.endswith("y"):
        preferred_ids.append(base_id + "megay")
    preferred_ids.append(base_id + "mega")
    for pid in preferred_ids:
        m = candidates[candidates["id"].apply(normalize_id) == normalize_id(pid)]
        if not m.empty:
            return {"status": "pass", "active_row": m.iloc[0], "form_trigger": "Mega Stone", "trigger_item": item_receipt.get("name", item_id)}

    # Fallback by display name: "Mega Gallade", "Mega Charizard X" etc.
    target_prefix = "mega" + normalize_id(base_name)
    possible = []
    for _, row in candidates.iterrows():
        rn = normalize_id(row.get("name", ""))
        if rn.startswith(target_prefix):
            possible.append(row)
    if len(possible) == 1:
        return {"status": "pass", "active_row": possible[0], "form_trigger": "Mega Stone", "trigger_item": item_receipt.get("name", item_id)}
    if len(possible) > 1:
        suffix = "x" if (item_id.endswith("itex") or item_name_norm.endswith("x")) else ("y" if (item_id.endswith("itey") or item_name_norm.endswith("y")) else "")
        for row in possible:
            if suffix and normalize_id(row.get("name", "")).endswith(suffix):
                return {"status": "pass", "active_row": row, "form_trigger": "Mega Stone", "trigger_item": item_receipt.get("name", item_id)}
        return {
            "status": "fail",
            "code": "FAIL_ACTIVE_FORM_MISSING",
            "reason": "multiple possible Mega forms; explicit active_form is required",
            "possible_active_forms": [{"id": r.get("id", ""), "name": r.get("name", "")} for r in possible],
        }
    return {
        "status": "fail",
        "code": "FAIL_ACTIVE_FORM_NOT_VERIFIED",
        "reason": "Mega Stone is local, but no matching Mega active form row was found in 01",
        "base_pokemon": base_id,
        "item": item_receipt.get("name", item_id),
    }


def _infer_state_active_form(base_row, ability_name: str, state: dict) -> dict | None:
    """Return an inferred state-form result or None if no state form applies."""
    pid = normalize_id(base_row["id"])
    ability_id = normalize_id(ability_name or ";".join([a.strip() for a in base_row.get("abilities", "").split(";")]))
    state = state or {}
    df = load_01_pokemon()

    # Palafin Zero to Hero: only allow Hero claim after explicit switch-out state.
    if pid == "palafin" and (state.get("has_switched_out") is True or state.get("zero_to_hero_triggered") is True):
        target_id = "palafinhero"
        match = df[df["id"].apply(normalize_id) == target_id]
        if match.empty:
            return {
                "status": "fail",
                "code": "FAIL_ACTIVE_FORM_NOT_VERIFIED",
                "reason": "Palafin Hero was claimed by state, but palafinhero is not present in local 01; do not use Hero stats",
                "required_state": {"has_switched_out": True},
            }
        if "zerotohero" not in ability_id:
            return {
                "status": "fail",
                "code": "FAIL_FORM_TRIGGER_NOT_VERIFIED",
                "reason": "Palafin Hero requires locally verified Zero to Hero ability",
            }
        return {"status": "pass", "active_row": match.iloc[0], "form_trigger": "Zero to Hero after switch-out", "state": state}

    # Aegislash Stance Change: if a stance is provided, use the matching local row.
    if pid in {"aegislash", "aegislashshield", "aegislashblade"}:
        stance = normalize_id(str(state.get("stance", state.get("form", ""))))
        target_id = None
        if stance in {"blade", "bladeform", "attack", "attacking"}:
            target_id = "aegislashblade"
        elif stance in {"shield", "shieldform", "defense", "defensive"}:
            target_id = "aegislashshield"
        if target_id:
            match = df[df["id"].apply(normalize_id) == target_id]
            if match.empty:
                return {"status": "fail", "code": "FAIL_ACTIVE_FORM_NOT_VERIFIED", "reason": f"{target_id} not found in local 01"}
            if "stancechange" not in ability_id:
                return {"status": "fail", "code": "FAIL_FORM_TRIGGER_NOT_VERIFIED", "reason": "Aegislash stance forms require locally verified Stance Change ability"}
            return {"status": "pass", "active_row": match.iloc[0], "form_trigger": f"Stance Change: {stance}", "state": state}
    return None


def resolve_active_combatant(slot, battle_state: dict | None = None) -> dict:
    """Resolve the active combatant row and battle ability for a team slot/side.

    Source of truth:
    - team_form: selected Pokémon row from 01
    - active_form: battle row after Mega/state/form trigger
    - battle_ability: must belong to active_form; base-form abilities do not pass for Mega/changed active forms
    - stat_source: active_form id; stat/damage/speed/type claims must use this row
    """
    if isinstance(slot, str):
        slot = {"pokemon": slot}
    slot = dict(slot or {})
    battle_state = battle_state or slot.get("state") or slot.get("battle_state") or {}
    pokemon_query = slot.get("pokemon") or slot.get("team_form") or slot.get("base_pokemon") or ""
    base_row = _find_pokemon_row(pokemon_query)
    if base_row is None:
        return {"entity": "active_form", "status": "fail", "code": "FAIL_TEAM_FORM_NOT_VERIFIED", "reason": "team/base Pokémon not found in 01", "pokemon_query": pokemon_query}

    team_form_receipt = _row_to_pokemon_receipt(base_row)
    item_receipt = verify_item(slot.get("item", "")) if slot.get("item") else {"status": "not_provided"}
    requested_active = slot.get("active_form") or slot.get("battle_form") or slot.get("stat_source") or ""
    active_row = base_row
    trigger = "team form"
    trigger_receipt = {"status": "not_required"}

    # Mega Stone auto-resolves active form unless explicit active_form is supplied and matches.
    if item_receipt.get("status") == "pass" and _is_mega_item_receipt(item_receipt):
        mega = _resolve_mega_form_from_item(base_row, item_receipt)
        trigger_receipt = {k: v for k, v in mega.items() if k != "active_row"}
        if mega.get("status") != "pass":
            return {
                "entity": "active_form",
                "status": "fail",
                "code": mega.get("code", "FAIL_ACTIVE_FORM_NOT_VERIFIED"),
                "team_form": team_form_receipt,
                "item_receipt": item_receipt,
                "trigger_receipt": mega,
                "reason": mega.get("reason", "Mega active form could not be resolved"),
            }
        active_row = mega["active_row"]
        trigger = mega.get("form_trigger", "Mega Stone")
        if requested_active and normalize_id(requested_active) not in {normalize_id(active_row["id"]), normalize_id(active_row["name"])}:
            return {
                "entity": "active_form",
                "status": "fail",
                "code": "FAIL_MEGA_ACTIVE_FORM_MISMATCH",
                "team_form": team_form_receipt,
                "item_receipt": item_receipt,
                "expected_active_form": {"id": active_row["id"], "name": active_row["name"]},
                "requested_active_form": requested_active,
                "reason": "explicit active_form does not match the Mega Stone resolved form",
            }
    else:
        # Explicit active form requires a verified non-Mega trigger/state.
        if requested_active:
            req_row = _find_pokemon_row(requested_active)
            if req_row is None:
                return {"entity": "active_form", "status": "fail", "code": "FAIL_ACTIVE_FORM_NOT_VERIFIED", "team_form": team_form_receipt, "requested_active_form": requested_active, "reason": "requested active_form not found in local 01"}
            if normalize_id(req_row["id"]) != normalize_id(base_row["id"]):
                inferred = _infer_state_active_form(base_row, slot.get("ability", slot.get("battle_ability", "")), battle_state)
                if not inferred or inferred.get("status") != "pass" or normalize_id(inferred["active_row"]["id"]) != normalize_id(req_row["id"]):
                    return {
                        "entity": "active_form",
                        "status": "fail",
                        "code": "FAIL_FORM_TRIGGER_NOT_VERIFIED",
                        "team_form": team_form_receipt,
                        "requested_active_form": {"id": req_row["id"], "name": req_row["name"]},
                        "reason": "active_form differs from team_form but no verified trigger/state supports it",
                        "required_examples": ["Mega Stone", "Palafin state.has_switched_out=true", "Aegislash state.stance=blade/shield"],
                    }
                active_row = inferred["active_row"]
                trigger = inferred.get("form_trigger", "state trigger")
                trigger_receipt = {k: v for k, v in inferred.items() if k != "active_row"}
            else:
                active_row = req_row
        else:
            inferred = _infer_state_active_form(base_row, slot.get("ability", slot.get("battle_ability", "")), battle_state)
            if inferred:
                if inferred.get("status") != "pass":
                    return {"entity": "active_form", "status": "fail", **inferred, "team_form": team_form_receipt}
                active_row = inferred["active_row"]
                trigger = inferred.get("form_trigger", "state trigger")
                trigger_receipt = {k: v for k, v in inferred.items() if k != "active_row"}

    active_receipt = _row_to_pokemon_receipt(active_row)
    active_changed = normalize_id(active_row["id"]) != normalize_id(base_row["id"])
    supplied_battle_ability = slot.get("battle_ability") or slot.get("ability") or ""
    active_abilities = active_receipt.get("abilities", [])
    battle_ability = supplied_battle_ability
    if active_changed:
        # For changed forms, final set ability must be the battle ability from active_form.
        if not battle_ability and len(active_abilities) == 1:
            battle_ability = active_abilities[0]
        ability_receipt = verify_ability_on_pokemon(active_row["id"], battle_ability) if battle_ability else {"status": "fail", "reason": "battle_ability required for active form"}
        if ability_receipt.get("status") != "pass":
            return {
                "entity": "active_form",
                "status": "fail",
                "code": "FAIL_ABILITY_USED_BASE_FORM_INSTEAD_OF_ACTIVE_FORM",
                "team_form": team_form_receipt,
                "active_form": active_receipt,
                "battle_ability_query": battle_ability,
                "active_form_abilities": active_abilities,
                "reason": "battle ability must be verified on active_form, not the base/team form",
                "ability_receipt": ability_receipt,
            }
    else:
        ability_receipt = verify_ability_on_pokemon(active_row["id"], battle_ability) if battle_ability else {"status": "not_provided"}

    display_name = active_receipt["name"] if not active_changed else f"{team_form_receipt['name']} → {active_receipt['name']}"
    return {
        "entity": "active_form",
        "status": "pass",
        "team_form": team_form_receipt,
        "active_form": active_receipt,
        "team_form_id": team_form_receipt["id"],
        "active_form_id": active_receipt["id"],
        "active_changed": active_changed,
        "form_trigger": trigger,
        "trigger_receipt": trigger_receipt,
        "item_receipt": item_receipt,
        "battle_ability": ability_receipt.get("ability_name", battle_ability),
        "battle_ability_receipt": ability_receipt,
        "stat_source": active_receipt["id"],
        "display_name": display_name,
        "rule": "team_form selects the roster slot; active_form is the battle stat/type/ability source. No active-form receipt = no form-based stat/damage/speed claim.",
    }


def verify_active_form(slot_or_scenario) -> dict:
    if isinstance(slot_or_scenario, dict) and ("attacker" in slot_or_scenario or "defender" in slot_or_scenario):
        return {
            "entity": "active_form_bundle",
            "status": "pass",
            "attacker": resolve_active_combatant(slot_or_scenario.get("attacker", {})),
            "defender": resolve_active_combatant(slot_or_scenario.get("defender", {})),
        }
    return resolve_active_combatant(slot_or_scenario)


TYPE_CHART = {
    "normal":   {"rock": 0.5, "ghost": 0.0, "steel": 0.5},
    "fire":     {"fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 2.0, "bug": 2.0, "rock": 0.5, "dragon": 0.5, "steel": 2.0},
    "water":    {"fire": 2.0, "water": 0.5, "grass": 0.5, "ground": 2.0, "rock": 2.0, "dragon": 0.5},
    "electric": {"water": 2.0, "electric": 0.5, "grass": 0.5, "ground": 0.0, "flying": 2.0, "dragon": 0.5},
    "grass":    {"fire": 0.5, "water": 2.0, "grass": 0.5, "poison": 0.5, "ground": 2.0, "flying": 0.5, "bug": 0.5, "rock": 2.0, "dragon": 0.5, "steel": 0.5},
    "ice":      {"fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 0.5, "ground": 2.0, "flying": 2.0, "dragon": 2.0, "steel": 0.5},
    "fighting": {"normal": 2.0, "ice": 2.0, "poison": 0.5, "flying": 0.5, "psychic": 0.5, "bug": 0.5, "rock": 2.0, "ghost": 0.0, "dark": 2.0, "steel": 2.0, "fairy": 0.5},
    "poison":   {"grass": 2.0, "poison": 0.5, "ground": 0.5, "rock": 0.5, "ghost": 0.5, "steel": 0.0, "fairy": 2.0},
    "ground":   {"fire": 2.0, "electric": 2.0, "grass": 0.5, "poison": 2.0, "flying": 0.0, "bug": 0.5, "rock": 2.0, "steel": 2.0},
    "flying":   {"electric": 0.5, "grass": 2.0, "fighting": 2.0, "bug": 2.0, "rock": 0.5, "steel": 0.5},
    "psychic":  {"fighting": 2.0, "poison": 2.0, "psychic": 0.5, "dark": 0.0, "steel": 0.5},
    "bug":      {"fire": 0.5, "grass": 2.0, "fighting": 0.5, "poison": 0.5, "flying": 0.5, "psychic": 2.0, "ghost": 0.5, "dark": 2.0, "steel": 0.5, "fairy": 0.5},
    "rock":     {"fire": 2.0, "ice": 2.0, "fighting": 0.5, "ground": 0.5, "flying": 2.0, "bug": 2.0, "steel": 0.5},
    "ghost":    {"normal": 0.0, "psychic": 2.0, "ghost": 2.0, "dark": 0.5},
    "dragon":   {"dragon": 2.0, "steel": 0.5, "fairy": 0.0},
    "dark":     {"fighting": 0.5, "psychic": 2.0, "ghost": 2.0, "dark": 0.5, "fairy": 0.5},
    "steel":    {"fire": 0.5, "water": 0.5, "electric": 0.5, "ice": 2.0, "rock": 2.0, "steel": 0.5, "fairy": 2.0},
    "fairy":    {"fire": 0.5, "fighting": 2.0, "poison": 0.5, "dragon": 2.0, "dark": 2.0, "steel": 0.5},
}

VALID_TYPES = set(TYPE_CHART.keys())
_TYPE_NAME = {
    "normal": "Normal", "fire": "Fire", "water": "Water", "electric": "Electric",
    "grass": "Grass", "ice": "Ice", "fighting": "Fighting", "poison": "Poison",
    "ground": "Ground", "flying": "Flying", "psychic": "Psychic", "bug": "Bug",
    "rock": "Rock", "ghost": "Ghost", "dragon": "Dragon", "dark": "Dark",
    "steel": "Steel", "fairy": "Fairy",
}

def _parse_type_token(text: str) -> str:
    return normalize_id(text)


def _parse_types_field(types_text: str):
    """Parse type strings from 01 or manual input into normalized lowercase types."""
    if not types_text:
        return []
    raw_parts = re.split(r"[/;,|+\s]+", str(types_text))
    out = []
    for part in raw_parts:
        key = _parse_type_token(part)
        if key in VALID_TYPES and key not in out:
            out.append(key)
    return out


def _defender_types_from_query(defender_query: str):
    row = _find_pokemon_row(defender_query)
    if row is not None:
        return _parse_types_field(row.get("types", "")), {
            "defender_kind": "pokemon",
            "pokemon_id": row.get("id", ""),
            "pokemon_name": row.get("name", defender_query),
            "source": "01",
        }
    parsed = _parse_types_field(defender_query)
    return parsed, {
        "defender_kind": "manual_types",
        "defender_query": defender_query,
        "source": "manual input",
    }


def verify_type_effectiveness(attacking_type: str, defender_query: str) -> dict:
    """Return a fail-closed dual-type effectiveness receipt.

    The important guard is product over every defender type. This prevents
    single-type shortcuts such as Fire -> Steel = 2x when the target is
    actually Steel/Dragon and therefore neutral overall.
    """
    atk = _parse_type_token(attacking_type)
    if atk not in VALID_TYPES:
        return {
            "entity": "type_effectiveness",
            "attacking_type_query": attacking_type,
            "defender_query": defender_query,
            "status": "fail",
            "reason": "attacking type not recognized in local type chart",
        }
    defender_types, defender_meta = _defender_types_from_query(defender_query)
    if not defender_types:
        return {
            "entity": "type_effectiveness",
            "attacking_type": _TYPE_NAME.get(atk, attacking_type),
            "defender_query": defender_query,
            "status": "fail",
            "reason": "defender Pokémon not found in 01 and no valid manual type pair was parsed",
        }
    per_type = []
    total = 1.0
    for d in defender_types:
        mult = float(TYPE_CHART.get(atk, {}).get(d, 1.0))
        total *= mult
        per_type.append({
            "attacking_type": _TYPE_NAME[atk],
            "defending_type": _TYPE_NAME[d],
            "multiplier": mult,
        })
    if total == 0.0:
        label = "immune"
    elif total < 1.0:
        label = "resisted"
    elif total == 1.0:
        label = "neutral"
    else:
        label = "super_effective"
    defender_type_names = [_TYPE_NAME[t] for t in defender_types]
    if float(total).is_integer():
        multiplier_display = str(int(total))
    else:
        multiplier_display = str(total).rstrip("0").rstrip(".")
    return {
        "entity": "type_effectiveness",
        "attacking_type": _TYPE_NAME[atk],
        "defender_query": defender_query,
        "defender": defender_meta,
        "defender_types": defender_type_names,
        "per_defender_type": per_type,
        "total_type_multiplier": total,
        "multiplier_display": multiplier_display + "x",
        "label": label,
        "display": f"{_TYPE_NAME[atk]} → {'/'.join(defender_type_names)} = {multiplier_display}x {label}",
        "source": "01 defender typing + bundled type chart in 09",
        "status": "pass",
        "rule": "No typechart receipt = no type effectiveness claim. Multiply the attacking type against every defender type; never infer immunity/resistance from memory.",
    }


MECHANIC_RULES = {
    "trickroom": {
        "entity": "mechanic",
        "id": "trickroom",
        "name": "Trick Room",
        "source": "00/04/09",
        "priority": -7,
        "status": "pass",
        "rule": "Trick Room has priority -7. A fast setter does not move before normal-priority attacks on the setup turn; it must survive until the -7 priority bracket.",
        "hard_invalid_claims": [
            "fast Trick Room setter moves first because of high Speed",
            "Speed stat makes Trick Room go before normal attacks",
        ],
    },
    "fakeout": {
        "entity": "mechanic",
        "id": "fakeout",
        "name": "Fake Out",
        "source": "00/04/09",
        "priority": 3,
        "status": "pass",
        "rule": "Fake Out is priority +3 and can flinch valid targets on the user's first turn after entering battle, subject to local targeting/block checks.",
    },
    "prankster": {
        "entity": "mechanic",
        "id": "prankster",
        "name": "Prankster support",
        "source": "00/04/09",
        "priority_delta": 1,
        "status": "pass",
        "rule": "Prankster gives +1 priority to eligible status support moves when no verified block applies.",
    },
    "prankstertailwind": {
        "entity": "mechanic",
        "id": "prankstertailwind",
        "name": "Prankster Tailwind",
        "source": "00/04/09",
        "priority": 1,
        "status": "pass",
        "rule": "Tailwind used by a verified Prankster user is treated as priority +1; Fake Out +3 acts before it unless a verified mechanic blocks Fake Out.",
    },
    "tailwind": {
        "entity": "mechanic",
        "id": "tailwind",
        "name": "Tailwind",
        "source": "00/04/09",
        "priority": 0,
        "status": "pass",
        "rule": "Tailwind is speed control; after it succeeds, use dynamic speed resolution for later actions. Do not combine it with Trick Room as one speed plan without explicit separation.",
    },
    "protect": {
        "entity": "mechanic",
        "id": "protect",
        "name": "Protect",
        "source": "00/04/09",
        "priority_note": "high-priority defensive bracket; verify move and local exceptions",
        "status": "pass",
        "rule": "Protect can block most attacks but must be exact-verified as a move on that Pokémon and checked against bypass moves/effects.",
    },
    "wideguard": {
        "entity": "mechanic",
        "id": "wideguard",
        "name": "Wide Guard",
        "source": "00/04/09",
        "priority_note": "high-priority spread protection bracket; verify move and local exceptions",
        "status": "pass",
        "rule": "Wide Guard protects the user's side from spread/wide-ranging attacks for the turn; verify the move and check whether the incoming move is actually spread/wide-ranging.",
    },
}

MECHANIC_ALIASES = {
    "tr": "trickroom",
    "trickroom": "trickroom",
    "trick room": "trickroom",
    "fakeout": "fakeout",
    "fake out": "fakeout",
    "prankster": "prankster",
    "prankstertailwind": "prankstertailwind",
    "prankster tailwind": "prankstertailwind",
    "tailwind": "tailwind",
    "protect": "protect",
    "wideguard": "wideguard",
    "wide guard": "wideguard",
    "priority": "priorityorder",
    "prio": "priorityorder",
    "priority order": "priorityorder",
}

# Conservative priority receipt table. This is not a move-legality source.
# A move still has to pass verify_move_on_pokemon() first.
# Unknown moves default to normal priority 0 for turn-order modelling unless another
# local mechanics source is supplied.
PRIORITY_MOVE_RULES = {
    # Defensive / support brackets
    "helpinghand": {"priority": 5, "note": "high-priority ally support"},
    "protect": {"priority": 4, "note": "defensive protection bracket"},
    "detect": {"priority": 4, "note": "defensive protection bracket"},
    "endure": {"priority": 4, "note": "survival protection bracket"},
    "wideguard": {"priority": 3, "note": "side protection against spread/wide-ranging moves"},
    "quickguard": {"priority": 3, "note": "side protection against priority moves"},
    "fakeout": {"priority": 3, "note": "first-turn flinch pressure; targeting/block checks still required"},
    "followme": {"priority": 2, "note": "redirection support"},
    "ragepowder": {"priority": 2, "note": "redirection support; powder/grass/ability exceptions must be checked separately if relevant"},
    "feint": {"priority": 2, "note": "priority attack / protection interaction must be checked locally"},
    # Common priority attacks
    "extremespeed": {"priority": 2, "note": "priority attack"},
    "firstimpression": {"priority": 2, "note": "priority attack; first-turn condition must be checked"},
    "aquajet": {"priority": 1, "note": "priority attack"},
    "bulletpunch": {"priority": 1, "note": "priority attack"},
    "iceshard": {"priority": 1, "note": "priority attack"},
    "machpunch": {"priority": 1, "note": "priority attack"},
    "quickattack": {"priority": 1, "note": "priority attack"},
    "shadowsneak": {"priority": 1, "note": "priority attack"},
    "suckerpunch": {"priority": 1, "note": "conditional priority attack; fails if target is not using an attacking move"},
    "vacuumwave": {"priority": 1, "note": "priority attack"},
    "watershuriken": {"priority": 1, "note": "priority attack"},
    "accelerock": {"priority": 1, "note": "priority attack"},
    # Conditional / negative priority examples often misordered by models
    "grassyglide": {"priority": 0, "conditional_priority": "+1 only if Grassy Terrain condition is verified", "note": "do not claim priority without verified terrain condition"},
    "focuspunch": {"priority": -3, "note": "negative priority / interruption condition"},
    "avalanche": {"priority": -4, "note": "negative priority attack"},
    "revenge": {"priority": -4, "note": "negative priority attack"},
    "counter": {"priority": -5, "note": "negative priority reaction move"},
    "mirrorcoat": {"priority": -5, "note": "negative priority reaction move"},
    "roar": {"priority": -6, "note": "negative priority phazing move"},
    "whirlwind": {"priority": -6, "note": "negative priority phazing move"},
    "dragontail": {"priority": -6, "note": "negative priority phazing attack"},
    "circlethrow": {"priority": -6, "note": "negative priority phazing attack"},
    "trickroom": {"priority": -7, "note": "speed order reversal starts only after setup succeeds; setter must survive to -7 bracket"},
}

MECHANIC_RULES["priorityorder"] = {
    "entity": "mechanic",
    "id": "priorityorder",
    "name": "Priority order",
    "source": "00/04/09 + verify.py priority table",
    "status": "pass",
    "rule": "Priority bracket is checked before Speed. Speed only orders Pokémon inside the same priority bracket. Prankster modifies eligible Status support moves by +1 only after ability and move are verified.",
    "hard_invalid_claims": [
        "faster Pokémon moves before higher-priority move",
        "fast Trick Room ignores priority -7",
        "Prankster boosts attacking moves",
    ],
}


def _types_from_slot_or_query(slot_or_query) -> tuple[list[str], dict]:
    """Resolve defender types from a slot object, Pokémon name, or manual type string."""
    if isinstance(slot_or_query, dict):
        slot = _as_dict(slot_or_query)
        if slot.get("types"):
            if isinstance(slot.get("types"), list):
                types = []
                for t in slot.get("types"):
                    nt = normalize_id(str(t))
                    if nt in VALID_TYPES and nt not in types:
                        types.append(nt)
                return types, {"defender_kind": "slot_types", "source": "scenario.types"}
            parsed = _parse_types_field(slot.get("types"))
            if parsed:
                return parsed, {"defender_kind": "slot_types", "source": "scenario.types"}
        name = _slot_name(slot)
        if name:
            return _defender_types_from_query(name)
        return [], {"defender_kind": "slot", "source": "scenario", "reason": "no pokemon/types"}
    return _defender_types_from_query(str(slot_or_query or ""))


def _scenario_bool(obj: dict, *keys, default=None):
    for k in keys:
        if k in obj:
            return _truthy(obj.get(k))
    return default


def _incoming_move_row(move_name: str):
    return _global_row("move", move_name) if move_name else None


def _incoming_category(move_name: str, incoming: dict) -> str:
    cat = incoming.get("category") or incoming.get("move_category") or ""
    if cat:
        return str(cat)
    row = _incoming_move_row(move_name)
    return str(row.get("category", "")) if row is not None else ""


def _incoming_is_powder_or_spore(move_name: str, incoming: dict) -> bool:
    if _truthy(incoming.get("is_powder") or incoming.get("powder") or incoming.get("is_spore") or incoming.get("spore")):
        return True
    row = _incoming_move_row(move_name)
    hay = ""
    if row is not None:
        hay = f"{row.get('name','')} {row.get('description','')} {row.get('extra','')}"
    else:
        hay = str(move_name)
    # Fail conservative: "Powder Snow" is an attacking ice move, not a powder/status disruption move.
    if normalize_id(move_name) == "powdersnow":
        return False
    return bool(re.search(r"(?i)\\b(powder|spore|spores|dust|soporific|numbing powder)\\b", hay))


def _typepassive_rule_applies(rule: dict, defender_types: list[str], incoming: dict, context: dict) -> tuple[bool, str]:
    dtype = normalize_id(rule.get("defender_type", ""))
    if dtype not in defender_types:
        return False, "defender does not have this type"
    kind = normalize_id(rule.get("trigger_kind", ""))
    trig = normalize_id(rule.get("trigger_name", ""))
    move = incoming.get("move") or incoming.get("name") or incoming.get("trigger_name") or ""
    move_id = normalize_id(str(move))
    status = normalize_id(str(incoming.get("status") or incoming.get("status_condition") or incoming.get("condition") or context.get("status") or ""))
    hazard = normalize_id(str(incoming.get("hazard") or incoming.get("field_hazard") or context.get("hazard") or context.get("field_hazard") or ""))
    weather = normalize_id(str(incoming.get("weather") or context.get("weather") or ""))
    ability = normalize_id(str(incoming.get("source_ability") or incoming.get("ability") or context.get("source_ability") or ""))
    category = normalize_id(_incoming_category(str(move), incoming))
    grounded = _scenario_bool(context, "grounded", "is_grounded", default=None)
    if grounded is None:
        grounded = _scenario_bool(incoming, "target_grounded", "grounded", default=None)
    grounded_unknown = grounded is None

    if kind == "move":
        return move_id == trig, "move match" if move_id == trig else "move mismatch"
    if kind == "movetag":
        if trig == "powderorspore":
            ok = _incoming_is_powder_or_spore(str(move), incoming)
            return ok, "powder/spore local tag/description match" if ok else "not locally identified as powder/spore"
    if kind == "ability":
        return ability == trig or normalize_id(str(incoming.get("ability_effect") or "")) == trig, "ability match" if ability == trig else "ability mismatch"
    if kind == "statuscondition":
        aliases = {"burned": "burn", "paralyzed": "paralysis", "paralysis": "paralysis", "poisoned": "poison", "badlypoisoned": "badlypoisoned", "badpoison": "badlypoisoned", "toxic": "badlypoisoned", "frozen": "freeze"}
        st = aliases.get(status, status)
        tr = aliases.get(trig, trig)
        return st == tr, "status condition match" if st == tr else "status mismatch"
    if kind == "fieldhazard":
        ok = hazard == trig or move_id == trig
        if ok and "notgrounded" in normalize_id(rule.get("condition", "")):
            if grounded_unknown:
                return False, "grounded state required before claiming hazard immunity"
            if grounded:
                return False, "target is grounded, so Flying-style hazard immunity does not apply"
        return ok, "hazard match" if ok else "hazard mismatch"
    if kind == "switchinhazard":
        ok = hazard == trig or move_id == trig
        if ok and "grounded" in normalize_id(rule.get("condition", "")):
            if grounded_unknown:
                return False, "grounded state required before claiming Toxic Spikes removal"
            if not grounded:
                return False, "target is not grounded, so switch-in hazard removal does not apply"
        return ok, "switch-in hazard match" if ok else "switch-in hazard mismatch"
    if kind == "weather":
        return weather == trig or move_id == trig, "weather match" if (weather == trig or move_id == trig) else "weather mismatch"
    if kind == "trapping":
        trap_terms = [status, normalize_id(str(incoming.get("effect") or "")), move_id, ability]
        ok = trig in trap_terms or any(t in {"trap", "trapped", "cannotescape", "cantescape", "shadowtag", "meanlook", "arenatrap"} for t in trap_terms)
        return ok, "trapping/cannot-escape match" if ok else "trapping mismatch"
    if kind == "abilitymove":
        # Dark-type passive: only opposing Prankster-boosted Status moves.
        side = normalize_id(str(incoming.get("side") or context.get("side") or incoming.get("source_side") or context.get("source_side") or "opponent"))
        is_ally = side in {"ally", "self", "own", "friendly"} or _truthy(incoming.get("ally"))
        ok = ability == "prankster" and category == "status" and not is_ally
        return ok, "opposing Prankster-boosted status move" if ok else "not opposing Prankster status"
    return False, "unrecognized trigger kind"


def verify_typepassive(scenario) -> dict:
    """Receipt for passive type/status/weather/hazard properties.

    This is separate from attacking type effectiveness. It answers claims like
    Dark blocking opposing Prankster Status, Rock gaining SpD in sand, Grass
    blocking powder/spore effects, grounded Poison removing Toxic Spikes, etc.
    """
    if not isinstance(scenario, dict):
        scenario = {"defender": scenario}
    defender = _as_dict(scenario.get("defender") or scenario.get("target") or scenario.get("pokemon") or scenario)
    incoming = _as_dict(scenario.get("incoming") or scenario.get("trigger") or scenario.get("move") or {})
    if isinstance(scenario.get("move"), str):
        incoming.setdefault("move", scenario.get("move"))
    context = _as_dict(scenario.get("context"))
    defender_types, defender_meta = _types_from_slot_or_query(defender)
    if not defender_types:
        return {"entity": "typepassive", "status": "fail", "reason": "defender type could not be resolved from 01 or scenario.types", "defender": defender, "source": "01/scenario"}
    rules_df = load_09_type_passive_properties()
    matches = []
    non_matches = []
    for _, row in rules_df.iterrows():
        r = row.to_dict()
        applies, why = _typepassive_rule_applies(r, defender_types, incoming, context)
        if applies:
            matches.append({
                "rule_id": r.get("rule_id", ""),
                "defender_type": r.get("defender_type", ""),
                "trigger_kind": r.get("trigger_kind", ""),
                "trigger_name": r.get("trigger_name", ""),
                "condition": r.get("condition", ""),
                "result": r.get("result", ""),
                "exception": r.get("exception", ""),
                "source_status": r.get("source_status", ""),
                "source_note": r.get("source_note", ""),
                "public_label": r.get("public_label", ""),
                "match_reason": why,
            })
        else:
            non_matches.append({"rule_id": r.get("rule_id", ""), "reason": why})
    if not matches:
        return {
            "entity": "typepassive",
            "status": "not_applicable",
            "defender": {"pokemon": _slot_name(defender), "types": [_TYPE_NAME.get(t,t) for t in defender_types], **defender_meta},
            "incoming": incoming,
            "context": context,
            "matches": [],
            "rule": "No matching local type passive receipt. Do not claim a type passive/status/weather/hazard property from memory.",
        }
    status = "pass"
    # Pass statuses are local because the 09 CSV is bundled source-of-truth.
    return {
        "entity": "typepassive",
        "mode": "type_passive_property_receipt",
        "status": status,
        "defender": {"pokemon": _slot_name(defender), "types": [_TYPE_NAME.get(t,t) for t in defender_types], **defender_meta},
        "incoming": incoming,
        "context": context,
        "matches": matches,
        "public_summary": "; ".join(m.get("public_label", m.get("rule_id", "")) for m in matches),
        "source": "09_type_passive_properties.csv",
        "rule": "No typepassive receipt = no type passive/status/weather/hazard claim. Typechart is not typepassive.",
    }


def verify_mechanic(mechanic_name: str) -> dict:
    """Return a local mechanic/priority receipt for high-risk Doubles planning claims.

    This is intentionally small and conservative. It covers project-locked mechanics
    that models frequently hallucinate or mis-order, especially Trick Room priority.
    """
    raw = mechanic_name or ""
    key = raw.strip().lower()
    compact = normalize_id(raw)
    lookup_key = MECHANIC_ALIASES.get(key) or MECHANIC_ALIASES.get(compact) or compact
    rule = MECHANIC_RULES.get(lookup_key)
    if not rule:
        return {
            "entity": "mechanic",
            "query": mechanic_name,
            "id": compact,
            "source": "00/04/09",
            "status": "fail",
            "reason": "mechanic not in bundled priority/mechanic receipt table; verify from 00/04/09 or explicit local mechanics source before using in final turn plan",
        }
    out = dict(rule)
    out["query"] = mechanic_name
    return out


def _ability_is_prankster(pokemon_name_or_id: str, ability_name: str) -> bool:
    if not ability_name:
        return False
    receipt = verify_ability_on_pokemon(pokemon_name_or_id, ability_name)
    return receipt.get("status") == "pass" and normalize_id(receipt.get("ability_name", ability_name)) == "prankster"


def verify_priority_on_pokemon(pokemon_name_or_id: str, move_name: str, ability_name: str = "") -> dict:
    """Verify a Pokémon's move locally, then return an effective priority receipt.

    This prevents two common failures:
    1. claiming a move has priority before proving the Pokémon has the move;
    2. claiming Prankster priority without proving the ability and Status category.
    """
    move_receipt = verify_move_on_pokemon(pokemon_name_or_id, move_name)
    out = {
        "entity": "priority_receipt",
        "pokemon_query": pokemon_name_or_id,
        "move_query": move_name,
        "ability_query": ability_name,
        "source": "05-07 move legality + 01 ability + 00/04/09 mechanics",
        "move": move_receipt,
    }
    if move_receipt.get("status") != "pass":
        out.update({
            "status": "fail",
            "reason": "move did not pass local Pokémon/form move lookup; priority cannot be evaluated",
        })
        return out

    move_id = normalize_id(move_receipt.get("move_id", move_name))
    move_rule = PRIORITY_MOVE_RULES.get(move_id, {"priority": 0, "note": "normal priority unless another local mechanics source says otherwise"})
    base_priority = int(move_rule.get("priority", 0))
    category = str(move_receipt.get("category", "")).strip().lower()

    prankster_applied = False
    ability_receipt = None
    if ability_name:
        ability_receipt = verify_ability_on_pokemon(pokemon_name_or_id, ability_name)
        out["ability"] = ability_receipt
        if ability_receipt.get("status") != "pass":
            out.update({
                "status": "fail",
                "reason": "ability did not pass local ability lookup; cannot apply ability-based priority such as Prankster",
            })
            return out
        prankster_applied = normalize_id(ability_receipt.get("ability_name", ability_name)) == "prankster" and category == "status"

    effective_priority = base_priority + (1 if prankster_applied else 0)
    out.update({
        "status": "pass",
        "move_id": move_id,
        "move_name": move_receipt.get("move_name", move_name),
        "category": move_receipt.get("category", ""),
        "base_priority": base_priority,
        "effective_priority": effective_priority,
        "prankster_applied": prankster_applied,
        "rule_note": move_rule.get("note", ""),
        "conditional_priority": move_rule.get("conditional_priority", ""),
        "priority_order_rule": "Priority bracket is checked before Speed. Speed only breaks ties inside the same priority bracket.",
        "caveat": "Targeting, immunity, terrain, Protect/Wide Guard, redirection, and ability/item exceptions still require board checks before a final turn command.",
    })
    if normalize_id(ability_name) == "prankster" and category != "status":
        out["prankster_not_applied_reason"] = "Prankster only modifies eligible Status support moves, not Physical/Special attacking moves."
    return out


PRIORITY_BLOCKER_ABILITIES = {
    "armortail": {
        "name": "Armor Tail",
        "scope": "user_side",
        "rule": "Blocks opposing priority moves aimed at the Pokémon or its ally on the same side while the ability holder is active.",
    },
    "queenlymajesty": {
        "name": "Queenly Majesty",
        "scope": "user_side",
        "rule": "Blocks opposing priority moves aimed at the Pokémon or its ally on the same side while the ability holder is active, if locally verified.",
    },
    "dazzling": {
        "name": "Dazzling",
        "scope": "user_side",
        "rule": "Blocks opposing priority moves aimed at the Pokémon or its ally on the same side while the ability holder is active, if locally verified.",
    },
}


def _as_dict(obj):
    return obj if isinstance(obj, dict) else {}


def _slot_name(slot: dict) -> str:
    slot = _as_dict(slot)
    return slot.get("pokemon") or slot.get("name") or slot.get("id") or ""


def _slot_ability(slot: dict) -> str:
    slot = _as_dict(slot)
    return slot.get("battle_ability") or slot.get("ability") or ""


def _verified_priority_blockers_on_side(target_side: dict) -> list:
    """Return verified side-priority blockers such as Armor Tail.

    The function accepts either:
    - {"pokemon":"Farigiraf", "ability":"Armor Tail"}
    - {"pokemon":"Farigiraf", "ability":"Armor Tail", "partner": {...}}
    - {"members":[{...}, {...}]}
    It verifies ability-on-Pokémon from 01 before treating it as a blocker.
    """
    side = _as_dict(target_side)
    members = []
    if isinstance(side.get("members"), list):
        members.extend([m for m in side.get("members") if isinstance(m, dict)])
    else:
        members.append(side)
        for k in ["partner", "side_partner", "ally"]:
            if isinstance(side.get(k), dict):
                members.append(side[k])
            elif isinstance(side.get(k), str) and side.get(k):
                members.append({"pokemon": side.get(k)})
    blockers = []
    for member in members:
        pkmn = _slot_name(member)
        ability = _slot_ability(member)
        if not pkmn or not ability:
            continue
        ar = verify_ability_on_pokemon(pkmn, ability)
        aid = normalize_id(ar.get("ability_id", ability)) if ar.get("status") == "pass" else normalize_id(ability)
        if ar.get("status") == "pass" and aid in PRIORITY_BLOCKER_ABILITIES:
            info = PRIORITY_BLOCKER_ABILITIES[aid]
            blockers.append({
                "pokemon": ar.get("pokemon_id", pkmn),
                "pokemon_query": pkmn,
                "ability": ar.get("ability_name", ability),
                "ability_id": aid,
                "ability_receipt": ar,
                "rule": info["rule"],
            })
    return blockers


def verify_interaction(scenario) -> dict:
    """Verify a mechanic relationship, not just the existence of entities.

    v29.21 mechanicinteractiongate examples:
    - Prankster Taunt/Encore into Farigiraf Armor Tail side => PASS_BLOCKED
    - Fake Out into Armor Tail side => PASS_BLOCKED
    - Trick Room setup => priority -7 warning/survival-plan requirement

    This is intentionally conservative. It does not claim full turn legality; it returns
    a relationship receipt that final team/item reasoning can cite.
    """
    if not isinstance(scenario, dict):
        return {"entity": "mechanic_interaction", "status": "fail", "reason": "interaction scenario must be a JSON object"}
    actor = _as_dict(scenario.get("actor") or scenario.get("attacker") or scenario.get("source"))
    target = _as_dict(scenario.get("target") or scenario.get("defender") or scenario.get("target_side"))
    context = _as_dict(scenario.get("context"))
    actor_pokemon = _slot_name(actor)
    actor_ability = _slot_ability(actor)
    actor_move = actor.get("move") or scenario.get("move") or ""
    matrix_receipt = verify_mechanic_matrix(scenario)
    if (not actor_pokemon or not actor_move):
        if matrix_receipt.get("status") != "not_applicable":
            matrix_receipt["entity"] = "mechanic_interaction"
            matrix_receipt["interaction_kind"] = "mechanic_matrix_only"
            return matrix_receipt
        return {
            "entity": "mechanic_interaction",
            "status": "fail",
            "code": "FAIL_MECHANIC_RELATIONSHIP_UNCHECKED",
            "reason": "actor.pokemon and actor.move are required unless the scenario matches a local mechanic matrix rule",
        }
    priority_receipt = verify_priority_on_pokemon(actor_pokemon, actor_move, actor_ability)
    move_receipt = priority_receipt.get("move", {})
    ability_receipt = priority_receipt.get("ability", {"status": "not_provided"})
    out = {
        "entity": "mechanic_interaction",
        "source": "05-07 move + 01 ability + 00/04/09 relationship rules",
        "actor": {"pokemon": actor_pokemon, "ability": actor_ability, "move": actor_move},
        "target": target,
        "context": context,
        "priority_receipt": priority_receipt,
        "move_receipt": move_receipt,
        "ability_receipt": ability_receipt,
        "status": "pass",
        "blocked": False,
        "warnings": [],
        "mechanic_matrix_receipt": matrix_receipt if matrix_receipt.get("status") != "not_applicable" else {},
        "rule": "No interaction receipt = no mechanic counter claim. Existence of move/ability is not enough.",
    }
    if priority_receipt.get("status") != "pass":
        out.update({
            "status": "fail",
            "code": "FAIL_PRIORITY_CLAIM_WITHOUT_INTERACTION_RECEIPT",
            "reason": "actor priority/move/ability could not be verified, so the relationship cannot be used in final reasoning",
        })
        return out

    effective_priority = int(priority_receipt.get("effective_priority", 0) or 0)
    move_id = normalize_id(priority_receipt.get("move_id", actor_move))
    target_members = target
    blockers = _verified_priority_blockers_on_side(target_members)
    out["target_side_priority_blockers"] = blockers

    if effective_priority > 0 and blockers:
        blocker = blockers[0]
        out.update({
            "status": "pass_blocked",
            "blocked": True,
            "blocked_by": blocker.get("ability"),
            "blocked_by_pokemon": blocker.get("pokemon_query"),
            "interaction": f"{actor_pokemon} {actor_ability} {priority_receipt.get('move_name', actor_move)} -> {blocker.get('ability')} side",
            "public_summary": f"{blocker.get('ability')} blocks opposing priority moves while the holder is active, so {actor_ability + ' ' if actor_ability else ''}{priority_receipt.get('move_name', actor_move)} is not a direct reason to spend an item slot on this target/side.",
            "team_implication": "Do not justify Mental Herb or another item as the main answer to this priority threat unless a non-priority/bypass scenario is separately verified.",
        })
        return out

    if move_id == "trickroom":
        out["warnings"].append({
            "code": "WARN_TRICK_ROOM_SETTER_STILL_NEEDS_SURVIVAL_PLAN",
            "detail": "Trick Room is priority -7; interaction receipt must be paired with Fake Out, Protect, redirection, Armor Tail/Fake Out blocking, or bulk plan.",
        })
    if effective_priority > 0 and not blockers:
        out.update({
            "interaction": f"{actor_pokemon} {actor_ability} {priority_receipt.get('move_name', actor_move)} -> target side",
            "public_summary": "The move has positive priority and no verified side priority blocker was found in this scenario.",
            "team_implication": "If this is a named meta threat, the team needs a verified answer such as Armor Tail, Protect, positioning, or another locally confirmed mechanic.",
        })
    else:
        out.update({
            "interaction": f"{actor_pokemon} {priority_receipt.get('move_name', actor_move)} -> target side",
            "public_summary": "No priority-block relationship was triggered by the current scenario.",
            "team_implication": "Use normal legality/type/damage/teamfit gates for this interaction unless another mechanic is specified.",
        })
    return out



SOUND_MOVE_KEYWORDS = re.compile(r"\b(sound|noise|voice|sing|song|echo|boom)\b", re.I)


def _global_row(entity_type: str, name_or_id: str):
    df = load_08_global()
    key = normalize_id(name_or_id)
    rows = df[df["entity_type"].str.lower() == entity_type.lower()]
    match = rows[(rows["_norm_id"] == key) | (rows["_norm_name"] == key)]
    if match.empty:
        return None
    return match.iloc[0]


def _global_entity_receipt(entity_type: str, name_or_id: str) -> dict:
    row = _global_row(entity_type, name_or_id)
    if row is None:
        return {"entity": entity_type, "query": name_or_id, "status": "fail", "source": "08", "reason": f"no {entity_type} row in 08"}
    return {
        "entity": entity_type,
        "query": name_or_id,
        "id": row.get("id", normalize_id(name_or_id)),
        "name": row.get("name", name_or_id),
        "description": row.get("description", ""),
        "source_status": row.get("source_status", ""),
        "source": "08",
        "status": "pass",
    }




def _receipt_ok(rec: dict) -> bool:
    return isinstance(rec, dict) and str(rec.get("status", "")).lower() in {"pass", "pass_blocked", "pass_with_warnings"}


def _desc_contains_stat_lower(rec: dict) -> bool:
    desc = str(rec.get("description", ""))
    return bool(re.search(r"(?i)lower(?:s|ing)?\s+(?:the\s+)?(?:target'?s\s+|opposing\s+Pokémon'?s\s+|its\s+)?(?:Attack|Defense|Sp\. Atk|Sp\. Def|Speed|stats?)", desc))


def _move_global_type(move_name: str) -> str:
    row = _global_row("move", move_name)
    return str(row.get("type", "")) if row is not None else ""


def _mechanic_receipt(entity_type: str, name_or_id: str) -> dict:
    rec = _global_entity_receipt(entity_type, name_or_id)
    rec["mechanic_provenance"] = "LOCAL_08_DESCRIPTION" if rec.get("status") == "pass" else "UNVERIFIED_MECHANIC"
    return rec


def verify_mechanic_matrix(scenario) -> dict:
    """Conservative ability/status/field/item relationship receipt.

    This is a small local-evidence matrix, not a battle simulator. It proves only
    what the local 08 descriptions and verified move/type receipts support. When
    a relationship is absent or under-specified, it returns `not_applicable` or
    `unverified_mechanic` instead of importing mainline memory.
    """
    if not isinstance(scenario, dict):
        return {"entity": "mechanic_matrix", "status": "fail", "reason": "scenario must be a JSON object"}
    actor = _as_dict(scenario.get("actor") or scenario.get("attacker") or scenario.get("source"))
    target = _as_dict(scenario.get("target") or scenario.get("defender") or scenario.get("target_side"))
    context = _as_dict(scenario.get("context"))
    move = actor.get("move") or scenario.get("move") or ""
    actor_ability = _slot_ability(actor) or actor.get("source_ability") or scenario.get("source_ability") or ""
    target_ability = _slot_ability(target) or target.get("target_ability") or scenario.get("target_ability") or ""
    actor_ability_id = normalize_id(actor_ability)
    target_ability_id = normalize_id(target_ability)
    move_id = normalize_id(move)
    ctx_norm = normalize_id(" ".join(f"{k}:{v}" for k, v in context.items()))

    receipts = []
    warnings = []
    results = []
    failures = []

    def add_ability(name):
        if name:
            rec = _mechanic_receipt("ability", name)
            receipts.append(rec)
            return rec
        return {"status": "not_provided"}
    def add_move(name):
        if name:
            rec = _mechanic_receipt("move", name)
            receipts.append(rec)
            return rec
        return {"status": "not_provided"}

    move_rec = add_move(move)
    actor_ab_rec = add_ability(actor_ability)
    target_ab_rec = add_ability(target_ability)

    contact_known = _truthy(context.get("contact") or context.get("direct_contact") or scenario.get("contact") or scenario.get("direct_contact"))
    contact_unknown = not ("contact" in context or "direct_contact" in context or "contact" in scenario or "direct_contact" in scenario)
    hp_full = _truthy(context.get("hp_full") or context.get("full_hp") or scenario.get("hp_full") or scenario.get("full_hp"))
    hp_unknown = not ("hp_full" in context or "full_hp" in context or "hp_full" in scenario or "full_hp" in scenario)

    # Ability/status/stat-change interactions.
    if actor_ability_id == "intimidate" and target_ability_id == "contrary":
        if _receipt_ok(actor_ab_rec) and _receipt_ok(target_ab_rec):
            results.append({"claim": "Intimidate stat drop vs Contrary", "status": "pass", "result": "Contrary reverses the verified Attack-lowering attempt from Intimidate.", "mechanic_provenance": "LOCAL_08_DESCRIPTION_CHAIN"})
        else:
            failures.append({"code": "FAIL_ABILITY_INTERACTION_WITHOUT_INTERACTION_RECEIPT", "detail": "Intimidate/Contrary local rows not both verified."})

    if move_id == "thunderwave" and target_ability_id == "contrary":
        if _receipt_ok(move_rec) and _receipt_ok(target_ab_rec):
            results.append({"claim": "Thunder Wave vs Contrary", "status": "pass", "result": "Thunder Wave locally paralyzes; it is not a stat-lowering receipt, so this interaction does not prove a Contrary reversal.", "mechanic_provenance": "LOCAL_08_DESCRIPTION_CHAIN"})
        else:
            failures.append({"code": "FAIL_STATUS_MECHANIC_CLAIM_WITHOUT_RECEIPT", "detail": "Thunder Wave/Contrary local rows not both verified."})

    if target_ability_id == "defiant" and actor_ability_id in {"intimidate"}:
        if _receipt_ok(actor_ab_rec) and _receipt_ok(target_ab_rec):
            results.append({"claim": "Intimidate stat drop vs Defiant", "status": "pass", "result": "Defiant reacts to a stat lowered by an opposing Pokémon; Intimidate locally lowers opposing Attack.", "mechanic_provenance": "LOCAL_08_DESCRIPTION_CHAIN"})

    # Contact ability interactions.
    if target_ability_id in {"mummy", "wanderingspirit"}:
        if _receipt_ok(target_ab_rec):
            if contact_known:
                result = "Contact changes the attacker's Ability to Mummy." if target_ability_id == "mummy" else "Contact exchanges Abilities with the Pokémon that hits it."
                results.append({"claim": f"direct-contact move into {target_ab_rec.get('name', target_ability)}", "status": "pass", "result": result, "mechanic_provenance": "LOCAL_08_DESCRIPTION"})
            else:
                warnings.append({"code": "WARN_CONTACT_DEPENDENT_ABILITY_NEEDS_CONTACT_RECEIPT", "detail": f"{target_ab_rec.get('name', target_ability)} only applies on direct contact; supply context.contact=true before using it as a counter route."})

    # Move self/stat-lowering + Contrary.
    if actor_ability_id == "contrary" and move_id in {"closecombat", "clangingscales"}:
        if _receipt_ok(move_rec) and _receipt_ok(actor_ab_rec) and _desc_contains_stat_lower(move_rec):
            results.append({"claim": f"{move_rec.get('name', move)} self stat drop vs Contrary", "status": "pass", "result": "The move locally lowers the user's stats and Contrary reverses stat changes affecting the Pokémon.", "mechanic_provenance": "LOCAL_08_DESCRIPTION_CHAIN"})
        else:
            failures.append({"code": "FAIL_ABILITY_INTERACTION_WITHOUT_INTERACTION_RECEIPT", "detail": "Move stat-drop + Contrary chain is not fully verified."})

    if move_id == "kingsshield" and (actor_ability_id == "contrary" or target_ability_id == "contrary"):
        if _receipt_ok(move_rec):
            if contact_known:
                results.append({"claim": "King's Shield contact Attack drop vs Contrary", "status": "pass", "result": "King's Shield locally lowers Attack of direct-contact attackers; if that attacker has Contrary, a separate stat-change receipt supports reversal.", "mechanic_provenance": "LOCAL_08_DESCRIPTION_CHAIN"})
            else:
                warnings.append({"code": "WARN_KINGS_SHIELD_CONTRARY_REQUIRES_CONTACT_RECEIPT", "detail": "King's Shield Attack drop is contact-dependent; do not claim Contrary reversal unless contact is verified."})

    # Sound / Soundproof / type-changing ability chains.
    sound_rec = _is_sound_based_move(move) if move else {"status": "not_provided"}
    if move:
        receipts.append(sound_rec)
    if target_ability_id == "soundproof" and move:
        if sound_rec.get("is_sound_based") and _receipt_ok(target_ab_rec):
            results.append({"claim": f"{move_rec.get('name', move)} vs Soundproof", "status": "pass", "result": "Soundproof gives full immunity to locally identified sound-based moves.", "mechanic_provenance": "LOCAL_08_DESCRIPTION_CHAIN"})
        elif sound_rec.get("status") == "n/a":
            failures.append({"code": "FAIL_SOUND_TAG_CLAIM_WITHOUT_RECEIPT", "detail": f"{move} is not locally identified as sound-based; cannot claim Soundproof blocks it."})
    if actor_ability_id == "pixilate" and move:
        mtype = _move_global_type(move)
        if _receipt_ok(actor_ab_rec) and normalize_id(mtype) == "normal":
            results.append({"claim": f"Pixilate {move_rec.get('name', move)}", "status": "pass", "result": "Pixilate locally changes Normal-type moves to Fairy-type. Sound status, if claimed, must come from the move description receipt separately.", "move_original_type": mtype, "move_sound_receipt_status": sound_rec.get("status"), "mechanic_provenance": "LOCAL_08_DESCRIPTION_CHAIN"})
        elif _receipt_ok(actor_ab_rec):
            warnings.append({"code": "WARN_PIXILATE_MOVE_NOT_NORMAL_TYPE_LOCALLY", "detail": f"Pixilate was verified, but {move} is not locally Normal-type in 08."})

    # Priority, accuracy, terrain/weather field mechanics.
    if actor_ability_id == "galewings" and move:
        mtype = _move_global_type(move)
        if _receipt_ok(actor_ab_rec) and normalize_id(mtype) == "flying":
            if hp_full:
                results.append({"claim": f"Gale Wings {move_rec.get('name', move)} priority", "status": "pass", "result": "Gale Wings locally gives priority to Flying-type moves while HP is full.", "mechanic_provenance": "LOCAL_08_DESCRIPTION_CHAIN"})
            elif hp_unknown:
                warnings.append({"code": "WARN_GALE_WINGS_REQUIRES_FULL_HP_RECEIPT", "detail": "Gale Wings priority is HP-full conditional; provide context.hp_full=true before claiming +1 priority."})
    if actor_ability_id == "noguard" and move:
        if _receipt_ok(actor_ab_rec):
            results.append({"claim": f"No Guard {move_rec.get('name', move)} accuracy", "status": "pass", "result": "No Guard locally raises accuracy of moves known by this Pokémon and moves targeting it to 100%. Do not extend this beyond accuracy without another receipt.", "mechanic_provenance": "LOCAL_08_DESCRIPTION"})
    if actor_ability_id == "electricsurge":
        eterrain = _mechanic_receipt("move", "Electric Terrain")
        receipts.append(eterrain)
        if _receipt_ok(actor_ab_rec):
            if scenario.get("claim_multiplier") or context.get("claim_multiplier") or re.search(r"1\.5|50%", str(scenario)):
                warnings.append({"code": "WARN_ELECTRIC_TERRAIN_NUMERIC_MULTIPLIER_NOT_IN_LOCAL_RECEIPT", "detail": "Local Electric Terrain receipt says Electric moves are powered up but does not provide a numeric 1.5x multiplier."})
            results.append({"claim": "Electric Surge field setup", "status": "pass", "result": "Electric Surge locally turns the ground into Electric Terrain; Electric Terrain locally powers up Electric-type moves. Numeric multiplier requires an explicit local damage/mechanic receipt.", "mechanic_provenance": "LOCAL_08_DESCRIPTION_CHAIN"})
    if move_id == "auroraveil":
        snowing = _truthy(context.get("snow") or context.get("snowing") or scenario.get("snow") or scenario.get("snowing"))
        if _receipt_ok(move_rec):
            if snowing:
                results.append({"claim": "Aurora Veil in snow", "status": "pass", "result": "Aurora Veil locally reduces physical and special damage for five turns and can be used only when it is snowing.", "mechanic_provenance": "LOCAL_08_DESCRIPTION"})
            else:
                warnings.append({"code": "WARN_AURORA_VEIL_REQUIRES_SNOW_RECEIPT", "detail": "Aurora Veil can be used only when it is snowing; provide context.snowing=true before claiming the setup line."})
    if normalize_id(context.get("weather", "")) == "snow" or move_id == "snowscape":
        snow_rec = _mechanic_receipt("move", "Snowscape")
        receipts.append(snow_rec)
        if _receipt_ok(snow_rec):
            results.append({"claim": "Snow / Snowscape Ice Defense", "status": "pass", "result": "Snowscape locally summons snow and boosts Defense stats of Ice types. Apply only to verified Ice-type targets.", "mechanic_provenance": "LOCAL_08_DESCRIPTION"})

    if not results and not warnings and not failures:
        return {"entity": "mechanic_matrix", "status": "not_applicable", "rule": "No recognized matrix relationship in this scenario."}
    status = "fail" if failures else ("pass_with_warnings" if warnings else "pass")
    return {
        "entity": "mechanic_matrix",
        "status": status,
        "actor": {"pokemon": _slot_name(actor), "ability": actor_ability, "move": move},
        "target": {"pokemon": _slot_name(target), "ability": target_ability},
        "context": context,
        "results": results,
        "warnings": warnings,
        "failures": failures,
        "receipts": receipts,
        "rule": "Entity verification is not mechanic verification. Mechanic claims require this receipt, verify.py mechanic, interaction, boardscan, damage, or typechart as appropriate.",
    }

def _is_sound_based_move(move_id_or_name: str) -> dict:
    """Local-only sound move classifier from 08 descriptions/names.

    This intentionally does not import mainline battle rules. If local data does
    not identify a move as sound/noise/voice-style, the receipt is N/A.
    """
    row = _global_row("move", move_id_or_name)
    if row is None:
        return {"entity": "sound_move_check", "move": move_id_or_name, "status": "fail", "reason": "global move row not found in 08"}
    hay = f"{row.get('name','')} {row.get('description','')} {row.get('extra','')}"
    is_sound = bool(SOUND_MOVE_KEYWORDS.search(hay))
    return {
        "entity": "sound_move_check",
        "move": row.get("name", move_id_or_name),
        "move_id": row.get("id", normalize_id(move_id_or_name)),
        "is_sound_based": is_sound,
        "evidence": row.get("description", ""),
        "source": "08 move description",
        "status": "pass" if is_sound else "n/a",
        "rule": "Sound classification is local-data-only; sound-vs-Protect bypass is not inferred from mainline memory.",
    }


def _truthy(x) -> bool:
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return bool(x)
    return normalize_id(str(x)) in {"true", "yes", "y", "1", "protect", "protected", "active"}


def verify_boardscan(scenario) -> dict:
    """Board-level move-target / ally interaction receipt.

    This gate exists for claims such as ally damage, Soundproof blocking, typing
    immunity, Protect/Wide Guard interactions, and spread move safety. It is not
    a full simulator; it returns conservative receipts and marks unverified
    mechanics rather than filling gaps from memory.
    """
    if not isinstance(scenario, dict):
        return {"mode": "board_scan", "status": "fail", "reason": "boardscan scenario must be a JSON object"}
    attacker = _as_dict(scenario.get("attacker") or scenario.get("actor") or scenario.get("source"))
    attacker_name = _slot_name(attacker) or scenario.get("attacker_pokemon") or scenario.get("pokemon") or ""
    move_name = scenario.get("move") or attacker.get("move") or ""
    if not attacker_name or not move_name:
        return {"mode": "board_scan", "status": "fail", "code": "FAIL_BOARDSCAN_MISSING_ATTACKER_OR_MOVE", "reason": "attacker.pokemon and move are required"}
    move_receipt = verify_move_on_pokemon(attacker_name, move_name)
    global_move = _global_entity_receipt("move", move_name)
    sound_receipt = _is_sound_based_move(move_name)
    targets = scenario.get("targets") or scenario.get("target") or scenario.get("defenders") or []
    if isinstance(targets, (str, dict)):
        targets = [targets]
    target_receipts = []
    failures = []
    warnings = []
    for raw_t in targets:
        target = _as_dict(raw_t)
        target_name = _slot_name(target)
        if not target_name:
            failures.append({"code": "FAIL_BOARDSCAN_TARGET_MISSING_POKEMON", "target": raw_t})
            continue
        pokemon_receipt = verify_pokemon(target_name)
        ability_name = _slot_ability(target)
        ability_receipt = verify_ability_on_pokemon(target_name, ability_name) if ability_name else {"status": "not_provided"}
        type_receipt = verify_type_effectiveness(move_receipt.get("type", global_move.get("type", "")), target_name) if move_receipt.get("status") == "pass" else {"status": "fail", "reason": "move not verified"}
        typepassive_receipt = verify_typepassive({"defender": target, "incoming": {"move": move_name, "category": global_move.get("category", move_receipt.get("category", "")), "source_ability": attacker.get("ability") or attacker.get("source_ability") or ""}, "context": scenario.get("context", {})})
        protected = _truthy(target.get("protect") or target.get("protected") or target.get("is_protected"))
        soundproof_receipt = _global_entity_receipt("ability", "Soundproof") if normalize_id(ability_name) == "soundproof" else {"status": "not_applicable"}
        ability_blocked = bool(sound_receipt.get("is_sound_based") and ability_receipt.get("status") == "pass" and normalize_id(ability_receipt.get("ability_name", "")) == "soundproof")
        type_mult = type_receipt.get("total_type_multiplier") if type_receipt.get("status") == "pass" else None
        type_immune = type_mult == 0.0
        protect_status = "not_active"
        if protected:
            protect_status = "NO_BYPASS_VERIFIED"
            if sound_receipt.get("is_sound_based"):
                warnings.append({"code": "WARN_SOUND_MOVE_PROTECT_BYPASS_NOT_LOCAL_VERIFIED", "target": target_name, "detail": "Do not claim this sound move bypasses Protect unless a local mechanic receipt is supplied."})
        if ability_blocked:
            final = "blocked_by_ability"
            result = "0 damage from Soundproof ability receipt"
        elif type_immune:
            final = "blocked_by_type_immunity"
            result = f"0 damage from typechart: {type_receipt.get('display')}"
        elif protected:
            final = "protect_interaction_unresolved_no_bypass_verified"
            result = "Protect is active; no local bypass receipt is present. Do not claim bypass."
        elif type_receipt.get("status") == "pass":
            final = "typechart_applies"
            result = type_receipt.get("display", "typechart applies")
        else:
            final = "unverified"
            result = "target interaction not fully verified"
        target_receipts.append({
            "target": target_name,
            "is_ally": bool(target.get("ally") or target.get("is_ally")),
            "pokemon_receipt": pokemon_receipt,
            "ability_receipt": ability_receipt,
            "soundproof_receipt": soundproof_receipt,
            "typechart_receipt": type_receipt,
            "typepassive_receipt": typepassive_receipt,
            "protected": protected,
            "protect_status": protect_status,
            "ability_blocked": ability_blocked,
            "type_immune": type_immune,
            "final_interaction": final,
            "public_summary": result,
        })
    status = "fail" if failures else ("pass_with_warnings" if warnings else "pass")
    return {
        "mode": "board_scan",
        "entity": "board_interaction_receipt",
        "status": status,
        "attacker": attacker_name,
        "move": move_name,
        "move_receipt": move_receipt,
        "global_move_receipt": global_move,
        "sound_move_receipt": sound_receipt,
        "targets": target_receipts,
        "failures": failures,
        "warnings": warnings,
        "rule": "No boardscan receipt = no move-target/ally-damage claim. Do not fill missing Protect, Soundproof, typing, spread, or ally interactions from memory.",
    }



def verify_counterroute(scenario) -> dict:
    """Receipt for ranking a Pokémon as a counter/check to a named threat.

    A hard-counter claim must have a route: typechart, speed/priority, ability/item
    interaction, boardscan, and/or damage receipt. This function does not invent
    damage or matchup facts; it gathers the receipts supplied or derivable locally.
    """
    if not isinstance(scenario, dict):
        return {"entity": "counter_route_receipt", "status": "fail", "reason": "counterroute scenario must be a JSON object"}
    candidate = scenario.get("candidate") or scenario.get("answer") or scenario.get("pokemon") or ""
    threat = scenario.get("threat") or scenario.get("opponent") or {}
    threat_name = threat if isinstance(threat, str) else (threat.get("pokemon") or threat.get("name") or "")
    threat_moves = scenario.get("threat_moves") or (threat.get("moves") if isinstance(threat, dict) else []) or []
    if isinstance(threat_moves, str):
        threat_moves = [threat_moves]
    receipts = []
    route = []
    failures = []
    warnings = []
    cand_rec = verify_pokemon(candidate) if candidate else {"status": "fail", "reason": "candidate missing"}
    receipts.append(cand_rec)
    if threat_name:
        thr_rec = verify_pokemon(threat_name)
        receipts.append(thr_rec)
        if thr_rec.get("status") != "pass":
            warnings.append({"code": "WARN_COUNTER_THREAT_NOT_LOCAL_VERIFIED", "threat": threat_name, "detail": "Use generic category unless this named threat has a local/entity receipt."})
    for mv in threat_moves:
        # Verify move globally first; if threat is local, verify on Pokémon too.
        gm = _mechanic_receipt("move", mv)
        receipts.append(gm)
        if cand_rec.get("status") == "pass" and gm.get("status") == "pass":
            tc = verify_type_effectiveness(gm.get("type", ""), candidate)
            receipts.append(tc)
            route.append({"route": "typechart", "move": gm.get("name", mv), "receipt": tc, "status": tc.get("status")})
        if threat_name and verify_pokemon(threat_name).get("status") == "pass":
            mr = verify_move_on_pokemon(threat_name, mv)
            receipts.append(mr)
    supplied = scenario.get("receipts") or {}
    has_speed = bool(scenario.get("speed_receipt") or supplied.get("speed") or scenario.get("speed_route"))
    has_damage = bool(scenario.get("damage_receipt") or supplied.get("damage") or scenario.get("damage_route"))
    has_interaction = bool(scenario.get("interaction_receipt") or supplied.get("interaction") or scenario.get("interaction_route"))
    has_priority = bool(scenario.get("priority_receipt") or supplied.get("priority") or scenario.get("priority_route"))
    if has_speed: route.append({"route": "speed", "status": "provided"})
    if has_damage: route.append({"route": "damage", "status": "provided"})
    if has_interaction: route.append({"route": "interaction", "status": "provided"})
    if has_priority: route.append({"route": "priority", "status": "provided"})
    hard = normalize_id(str(scenario.get("claim", "") or scenario.get("rank", ""))) in {"hardcounter", "hardcheck", "hardanswer"} or _truthy(scenario.get("hard_counter"))
    type_ok = any(r.get("route") == "typechart" and r.get("receipt", {}).get("status") == "pass" for r in route)
    route_count = sum(1 for r in route if str(r.get("status", "")).lower() in {"pass", "provided"})
    if hard and route_count < 2:
        failures.append({"code": "FAIL_COUNTER_RANK_WITHOUT_ROUTE_RECEIPTS", "detail": "Hard counter/check claims need at least two verified route dimensions such as type + speed/damage/interaction."})
    status = "fail" if failures else ("pass_with_warnings" if warnings else "pass")
    return {
        "entity": "counter_route_receipt",
        "status": status,
        "candidate": candidate,
        "threat": threat_name,
        "threat_moves": threat_moves,
        "route": route,
        "receipts": receipts,
        "failures": failures,
        "warnings": warnings,
        "rule": "No counterroute receipt = no hard-counter / hard-check / best-answer claim. A route must cite type, speed, priority, ability/item/field, board, or damage receipts.",
    }

def _team_has_ability(team_receipt: dict, ability_id: str) -> list:
    out = []
    for r in team_receipt.get("sets", []):
        ar = r.get("ability", {})
        if ar.get("status") == "pass" and normalize_id(ar.get("ability_id", ar.get("ability_name", ""))) == ability_id:
            out.append({
                "slot": r.get("slot"),
                "pokemon": r.get("active_form", {}).get("display_name", r.get("pokemon_gate", {}).get("name", "")),
                "ability": ar.get("ability_name"),
            })
    return out


def _team_moves_by_id(team_receipt: dict) -> set:
    return {normalize_id(m.get("move_id", m.get("move_query", ""))) for r in team_receipt.get("sets", []) for m in r.get("moves", []) if m.get("status") == "pass"}


def _default_meta_threats_from_team(team_receipt: dict) -> list:
    """Infer common threat categories worth explaining if no explicit meta_threats are supplied.

    This is not a live meta source. It creates a local checklist only when the team
    itself contains relevant answers/claims, so render can explain the mechanics.
    """
    threats = []
    if _team_has_ability(team_receipt, "armortail"):
        threats.append({"name": "Prankster disruption", "examples": ["Whimsicott Taunt", "Whimsicott Encore"], "frequency": "contextual"})
        threats.append({"name": "Fake Out pressure", "examples": ["Fake Out"], "frequency": "contextual"})
    moves = _team_moves_by_id(team_receipt)
    if "trickroom" in moves:
        threats.append({"name": "Trick Room denial", "examples": ["Taunt", "Fake Out", "double target"], "frequency": "contextual"})
    if "earthquake" in moves:
        threats.append({"name": "Spread ally damage", "examples": ["Earthquake"], "frequency": "self-risk"})
    return threats


def _normalize_threats(meta_threats) -> list:
    if meta_threats is None:
        return []
    if isinstance(meta_threats, dict):
        meta_threats = meta_threats.get("meta_threats") or meta_threats.get("threats") or []
    if not isinstance(meta_threats, list):
        return []
    out = []
    for t in meta_threats:
        if isinstance(t, str):
            out.append({"name": t, "examples": [t]})
        elif isinstance(t, dict):
            out.append(t)
    return out


def evaluate_threat_fit(team_receipt: dict, meta_threats=None) -> dict:
    threats = _normalize_threats(meta_threats)
    if not threats:
        threats = _default_meta_threats_from_team(team_receipt)
    out = {
        "entity": "meta_threat_fit_receipt",
        "status": "pass",
        "source": "team receipt + interaction receipts + optional approved meta threat list",
        "threats_checked": [],
        "warnings": [],
        "failures": [],
        "rule": "No threatfit receipt = no 'team answers X' claim. Meta threat names must be connected to verified mechanics and team answers.",
    }
    armor_users = _team_has_ability(team_receipt, "armortail")
    moves = _team_moves_by_id(team_receipt)
    for threat in threats:
        name = threat.get("name", "unknown threat")
        norm = normalize_id(name + " " + " ".join(threat.get("examples", []) if isinstance(threat.get("examples"), list) else []))
        row = {"threat": name, "examples": threat.get("examples", []), "frequency": threat.get("frequency", "unknown"), "team_answer": "", "interaction_status": "not_checked", "item_implication": "", "remaining_risk": "", "status": "pass"}
        if "prankster" in norm or "taunt" in norm or "encore" in norm:
            if armor_users:
                row.update({
                    "team_answer": "; ".join(f"{u['pokemon']} {u['ability']}" for u in armor_users),
                    "interaction_status": "PASS_BLOCKED_FOR_PRIORITY_VARIANTS",
                    "item_implication": "Do not justify Mental Herb mainly for Prankster Taunt/Encore; Armor Tail already covers opposing priority while active.",
                    "remaining_risk": "Non-priority Taunt/Encore, ability suppression, or scenarios where the Armor Tail user is not on field still need separate receipts.",
                })
                out["warnings"].append({"code": "WARN_MENTAL_HERB_REASON_INVALID_VS_PRANKSTER_ARMOR_TAIL", "detail": "If Farigiraf/Armor Tail is active, Mental Herb should not be sold as the main answer to Prankster Taunt/Encore."})
            else:
                row.update({"status": "fail", "team_answer": "none verified", "interaction_status": "FAIL_TEAMFIT_THREAT_ANSWER_UNVERIFIED", "remaining_risk": "Prankster disruption named but no local side-priority blocker was verified."})
                out["failures"].append({"code": "FAIL_TEAMFIT_THREAT_ANSWER_UNVERIFIED", "threat": name})
        elif "fakeout" in norm or "fake out" in name.lower():
            if armor_users:
                row.update({
                    "team_answer": "; ".join(f"{u['pokemon']} {u['ability']}" for u in armor_users),
                    "interaction_status": "PASS_BLOCKED_WHILE_ARMOR_TAIL_ACTIVE",
                    "item_implication": "Lead plans may rely on Armor Tail only while the ability holder is on field.",
                    "remaining_risk": "If the Armor Tail holder is absent, Fake Out pressure must be answered by Protect, positioning, or another verified mechanic.",
                })
                out["warnings"].append({"code": "WARN_FAKE_OUT_PLAN_DEPENDS_ON_ARMOR_TAIL_FIELD_PRESENCE", "detail": "Armor Tail protects the side only while its holder is active."})
            else:
                row.update({"status": "warn", "team_answer": "Protect/positioning required", "interaction_status": "NO_SIDE_BLOCKER_VERIFIED", "remaining_risk": "Fake Out pressure needs lead-specific planning."})
        elif "trickroom" in norm or "trick room" in name.lower():
            row.update({
                "team_answer": "Trick Room setup plan",
                "interaction_status": "WARN_PRIORITY_MINUS_7_SURVIVAL_REQUIRED" if "trickroom" in moves else "NO_TRICK_ROOM_ON_TEAM",
                "item_implication": "TR setter items should address threats not already covered by Armor Tail/lead support.",
                "remaining_risk": "TR still acts at -7 and needs Fake Out/Protect/redirection/bulk unless board state proves safety.",
                "status": "warn",
            })
            out["warnings"].append({"code": "WARN_TRICK_ROOM_SETTER_STILL_NEEDS_SURVIVAL_PLAN", "detail": "Trick Room setup cannot be justified by Speed; it needs a survival plan."})
        elif "spread" in norm or "earthquake" in norm:
            row.update({"team_answer": "spread-move ally safety matrix", "interaction_status": "CHECK_PUBLIC_RENDER_MATRIX", "item_implication": "Do not describe spread attacks as free unless ally matrix is safe.", "remaining_risk": "Unsafe partners must Protect/switch or avoid the move."})
        else:
            row.update({"status": "warn", "team_answer": "not mapped", "interaction_status": "UNMAPPED_THREAT", "remaining_risk": "Add an explicit interaction scenario if this threat is used in final claims."})
            out["warnings"].append({"code": "WARN_UNMAPPED_META_THREAT", "threat": name, "detail": "Threat is listed but not mapped to a verifier interaction pattern."})
        out["threats_checked"].append(row)
    if out["failures"]:
        out["status"] = "fail"
    elif out["warnings"]:
        out["status"] = "pass_with_warnings"
    return out


def verify_threatfit(team_payload, meta_threats=None) -> dict:
    team_receipt = verify_team(team_payload) if not (isinstance(team_payload, dict) and team_payload.get("mode") == "full_team_verification") else team_payload
    return evaluate_threat_fit(team_receipt, meta_threats)



STAT_KEYS = ["hp", "atk", "def", "spa", "spd", "spe"]
STAT_KEY_ALIASES = {
    "hp": "hp",
    "hitpoints": "hp",
    "atk": "atk",
    "attack": "atk",
    "def": "def",
    "defense": "def",
    "spa": "spa",
    "spatk": "spa",
    "specialattack": "spa",
    "spattack": "spa",
    "spdef": "spd",
    "specialdefense": "spd",
    "specialdefence": "spd",
    "spd": "spd",
    "spe": "spe",
    "speed": "spe",
}


def _coerce_spread(spread_input):
    """Return (spread_dict, parse_note) or (None, note).

    Accepts:
    - dict with hp/atk/def/spa/spd/spe aliases
    - list/tuple of six values in HP/Atk/Def/SpA/SpD/Spe order
    - string containing six integers in that order
    """
    if spread_input is None or spread_input == "":
        return None, "missing spread"

    if isinstance(spread_input, dict):
        out = {}
        for k, v in spread_input.items():
            nk = STAT_KEY_ALIASES.get(normalize_id(str(k)))
            if nk:
                try:
                    out[nk] = int(v)
                except (TypeError, ValueError):
                    return None, f"spread value for {k} is not an integer"
        if set(out) != set(STAT_KEYS):
            missing = [k for k in STAT_KEYS if k not in out]
            return None, f"spread dict missing keys: {missing}"
        return out, "dict"

    if isinstance(spread_input, (list, tuple)):
        if len(spread_input) != 6:
            return None, "spread list must have 6 values"
        try:
            return {k: int(v) for k, v in zip(STAT_KEYS, spread_input)}, "list"
        except (TypeError, ValueError):
            return None, "spread list contains non-integer values"

    if isinstance(spread_input, str):
        nums = [int(x) for x in re.findall(r"-?\d+", spread_input)]
        if len(nums) != 6:
            return None, "spread string must contain exactly 6 integers in HP/Atk/Def/SpA/SpD/Spe order"
        return {k: v for k, v in zip(STAT_KEYS, nums)}, "string"

    return None, f"unsupported spread type: {type(spread_input).__name__}"



STAT_DISPLAY_NAMES = {
    "hp": "HP", "atk": "Atk", "def": "Def", "spa": "SpA", "spd": "SpD", "spe": "Spe"
}


def _spread_display_fields(spread: dict) -> dict:
    """Return copy-safe, labelled spread render fields.

    Public output should never show a bare 32/0/32/0/2/0 string.
    """
    if not isinstance(spread, dict):
        return {"compact": "", "verbose": "", "slash_with_header": "Order: HP / Atk / Def / SpA / SpD / Spe; Spread: ", "total": "0/66"}
    parts_compact = [f"{STAT_DISPLAY_NAMES[k]}{int(spread.get(k, 0) or 0)}" for k in STAT_KEYS]
    parts_verbose = [f"{STAT_DISPLAY_NAMES[k]} {int(spread.get(k, 0) or 0)}" for k in STAT_KEYS]
    slash = " / ".join(str(int(spread.get(k, 0) or 0)) for k in STAT_KEYS)
    total = sum(int(spread.get(k, 0) or 0) for k in STAT_KEYS)
    return {
        "compact": " ".join(parts_compact),
        "verbose": " / ".join(parts_verbose),
        "slash_with_header": f"Order: HP / Atk / Def / SpA / SpD / Spe; Spread: {slash}",
        "total": f"{total}/66",
        "order": "HP / Atk / Def / SpA / SpD / Spe",
    }


def _stat_display_fields(stats: dict) -> dict:
    if not isinstance(stats, dict) or not stats:
        return {"compact": "", "verbose": ""}
    parts = [f"{STAT_DISPLAY_NAMES[k]} {int(stats.get(k, 0) or 0)}" for k in STAT_KEYS]
    return {"compact": " / ".join(parts), "verbose": " / ".join(parts)}


def _move_display_list(move_receipts: list) -> list:
    return [m.get("display") or (f"{m.get('emoji','')} {m.get('move_name', m.get('move_query',''))}".strip()) for m in move_receipts if m.get("status") == "pass"]


def _spread_reason_for_slot(inp: dict, set_receipt: dict, teamfit_slot: dict, modes: list) -> list:
    """Generate short, labelled spread reasoning for public readable render.

    This is intentionally conservative and framed as team-fit explanation, not
    damage proof unless a damage benchmark receipt exists.
    """
    spread = set_receipt.get("spread", {}).get("spread", {}) or {}
    role = str(inp.get("role", "")).strip()
    speed_role = teamfit_slot.get("speed_role") or _set_speed_role(inp, set_receipt, modes)
    reasons = []
    hp = int(spread.get("hp", 0) or 0); atk = int(spread.get("atk", 0) or 0); df = int(spread.get("def", 0) or 0)
    spa = int(spread.get("spa", 0) or 0); spd = int(spread.get("spd", 0) or 0); spe = int(spread.get("spe", 0) or 0)
    if hp >= 28:
        reasons.append(f"HP {hp} เพื่อเพิ่ม bulk รวมและยืนในบอร์ด 2v2 ได้นานขึ้น")
    if atk >= 28:
        reasons.append(f"Atk {atk} เพราะ slot นี้ใช้ physical damage เป็นแรงกดหลัก")
    if spa >= 28:
        reasons.append(f"SpA {spa} เพราะ slot นี้ใช้ special damage เป็นแรงกดหลัก")
    if df >= 28:
        reasons.append(f"Def {df} เพื่อรับ physical damage/ยืนคู่กับแผน pivot หรือ setup")
    if spd >= 28:
        reasons.append(f"SpD {spd} เพื่อรับ special damage และลดโอกาสโดนลบก่อนทำหน้าที่")
    if spe >= 28:
        reasons.append(f"Spe {spe} เพื่อทำงานใน fast mode / Tailwind pressure")
    elif spe == 0 and "trick_room" in modes:
        reasons.append("Spe 0 เพื่อไม่ขัดแผน Trick Room")
    elif 1 <= spe <= 8:
        reasons.append(f"Spe {spe} เป็นแต้มต่ำ/แต้มเหลือ ไม่ได้ commit เข้า speed race")
    elif 9 <= spe <= 24:
        reasons.append(f"Spe {spe} เป็น bridge speed: พอช่วยใน Tailwind แต่ไม่สุดทางจนเสียค่าใน Trick Room")
    if "tailwind" in modes and "trick_room" in modes and speed_role == "BRIDGE_SPEED":
        reasons.append("ทีมมีทั้ง Tailwind และ Trick Room จึงวาง speed แบบกลาง ไม่ยัด full Speed/Choice Scarf โดยไม่มีเหตุผล")
    if role:
        reasons.append(f"Role อ้างอิงจากทีม: {role}")
    # Keep output short.
    return reasons[:5] if reasons else ["สเปรดนี้ผ่าน 0-32/66 gate แล้ว แต่ยังไม่มี benchmark เฉพาะ ต้องอธิบายเพิ่มถ้านำไปใช้จริง"]


def verify_spread(spread_input) -> dict:
    spread, parse_note = _coerce_spread(spread_input)
    if spread is None:
        return {
            "entity": "stat_spread",
            "source": "00/09",
            "status": "fail",
            "reason": parse_note,
        }

    over = {k: v for k, v in spread.items() if v > 32}
    under = {k: v for k, v in spread.items() if v < 0}
    total = sum(spread.values())
    ev_style = any(v >= 100 for v in spread.values()) or any(v == 252 for v in spread.values())

    if ev_style or over or under or total != 66:
        reasons = []
        if ev_style:
            reasons.append("EV-style/mainline spread detected; Pokémon Champions uses 0-32 investment, never 252 EV notation")
        if over:
            reasons.append(f"stat investment above 32: {over}")
        if under:
            reasons.append(f"negative stat investment: {under}")
        if total != 66:
            reasons.append(f"spread total is {total}, expected 66")
        return {
            "entity": "stat_spread",
            "source": "00/09",
            "status": "fail",
            "spread": spread,
            "total": total,
            "reason": "; ".join(reasons),
        }

    display_fields = _spread_display_fields(spread)
    return {
        "entity": "stat_spread",
        "source": "00/09",
        "status": "pass",
        "spread": spread,
        "order": "HP/Atk/Def/SpA/SpD/Spe",
        "total": total,
        "display": display_fields["verbose"] + "; Total " + display_fields["total"],
        "display_compact": display_fields["compact"],
        "display_verbose": display_fields["verbose"],
        "display_slash_with_header": display_fields["slash_with_header"],
        "display_total": display_fields["total"],
        "parse_note": parse_note,
        "render_rule": "Public output must show stat labels. Bare 32/0/32/0/2/0 format is invalid unless the stat order header is printed beside it.",
    }




NATURE_MODIFIERS = {
    "hardy": {}, "docile": {}, "bashful": {}, "quirky": {}, "serious": {},
    "lonely": {"atk": 1.1, "def": 0.9},
    "brave": {"atk": 1.1, "spe": 0.9},
    "adamant": {"atk": 1.1, "spa": 0.9},
    "naughty": {"atk": 1.1, "spd": 0.9},
    "bold": {"def": 1.1, "atk": 0.9},
    "relaxed": {"def": 1.1, "spe": 0.9},
    "impish": {"def": 1.1, "spa": 0.9},
    "lax": {"def": 1.1, "spd": 0.9},
    "timid": {"spe": 1.1, "atk": 0.9},
    "hasty": {"spe": 1.1, "def": 0.9},
    "jolly": {"spe": 1.1, "spa": 0.9},
    "naive": {"spe": 1.1, "spd": 0.9},
    "modest": {"spa": 1.1, "atk": 0.9},
    "mild": {"spa": 1.1, "def": 0.9},
    "quiet": {"spa": 1.1, "spe": 0.9},
    "rash": {"spa": 1.1, "spd": 0.9},
    "calm": {"spd": 1.1, "atk": 0.9},
    "gentle": {"spd": 1.1, "def": 0.9},
    "sassy": {"spd": 1.1, "spe": 0.9},
    "careful": {"spd": 1.1, "spa": 0.9},
}


def _nature_key(nature: str) -> str:
    return normalize_id(nature)


def _nature_multiplier(nature: str, stat_key: str):
    key = _nature_key(nature)
    if key not in NATURE_MODIFIERS:
        return None
    return float(NATURE_MODIFIERS[key].get(stat_key, 1.0))


def verify_stat(pokemon_name_or_id: str, nature: str, spread_input, state_input=None) -> dict:
    """Compute Pokémon Champions displayed stats through the active-form resolver.

    Formula locked by the project:
    HP = Base HP + 75 + HP investment
    Non-HP = floor((Base + 20 + investment) * nature_modifier)

    The stat source is the resolved active_form, not blindly the team/base form.
    Mega/Palafin/Aegislash-style claims require an active-form receipt.
    """
    slot = {"pokemon": pokemon_name_or_id}
    if isinstance(state_input, dict):
        # Allow either direct slot fields or nested state.
        slot.update({k: v for k, v in state_input.items() if k not in {"spread", "nature"}})
        if "state" not in slot and any(k in state_input for k in ["has_switched_out", "zero_to_hero_triggered", "stance", "form", "mega_evolved"]):
            slot["state"] = state_input
    active_receipt = resolve_active_combatant(slot)
    spread_receipt = verify_spread(spread_input)
    nkey = _nature_key(nature)
    if active_receipt.get("status") != "pass":
        return {"entity": "displayed_stats", "status": "fail", "reason": "active-form gate failed", "active_form_receipt": active_receipt}
    pokemon_receipt = active_receipt["active_form"]
    if spread_receipt.get("status") != "pass":
        return {"entity": "displayed_stats", "status": "fail", "reason": "spread gate failed", "active_form_receipt": active_receipt, "spread_receipt": spread_receipt}
    if nkey not in NATURE_MODIFIERS:
        return {
            "entity": "displayed_stats",
            "pokemon": pokemon_name_or_id,
            "nature_query": nature,
            "status": "fail",
            "reason": "unknown nature; nature must be one of the project nature enum values",
            "known_natures": sorted(NATURE_MODIFIERS.keys()),
            "active_form_receipt": active_receipt,
        }

    base = {k: int(pokemon_receipt["stats"][k]) for k in STAT_KEYS}
    spread = spread_receipt["spread"]
    stats = {"hp": base["hp"] + 75 + spread["hp"]}
    formula_steps = {"hp": f"{base['hp']} + 75 + {spread['hp']} = {stats['hp']}"}
    for k in ["atk", "def", "spa", "spd", "spe"]:
        mult = _nature_multiplier(nkey, k)
        value = math.floor((base[k] + 20 + spread[k]) * mult)
        stats[k] = value
        formula_steps[k] = f"floor(({base[k]} + 20 + {spread[k]}) * {mult}) = {value}"
    return {
        "entity": "displayed_stats",
        "pokemon_id": pokemon_receipt["id"],
        "pokemon_name": pokemon_receipt["name"],
        "team_form_id": active_receipt.get("team_form_id"),
        "active_form_id": active_receipt.get("active_form_id"),
        "stat_source": active_receipt.get("stat_source"),
        "display_name": active_receipt.get("display_name", pokemon_receipt["name"]),
        "active_form_receipt": active_receipt,
        "nature": nkey.capitalize(),
        "spread": spread,
        "base_stats": base,
        "displayed_stats": stats,
        "displayed_stats_display": _stat_display_fields(stats),
        "spread_display": _spread_display_fields(spread),
        "formula": "HP = Base + 75 + investment; Non-HP = floor((Base + 20 + investment) * nature_modifier)",
        "formula_steps": formula_steps,
        "source": "01 active-form base stats + 00/09 stat formula + verify.py stat",
        "status": "pass",
        "rule": "No active-form receipt = no form-based stat/speed/damage claim. Mega/state forms use active_form as stat_source.",
    }


def _load_json_arg(raw: str):
    """Read JSON from a file path or parse raw JSON string."""
    if os.path.exists(raw):
        with open(raw, "r", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(raw)


def _stat_stage_multiplier(stage) -> float:
    try:
        s = int(stage)
    except Exception:
        s = 0
    s = max(-6, min(6, s))
    if s >= 0:
        return (2 + s) / 2
    return 2 / (2 - s)


def _get_types_for_pokemon(pokemon_name_or_id: str):
    row = _find_pokemon_row(pokemon_name_or_id)
    if row is None:
        return []
    return _parse_types_field(row.get("types", ""))


def _weather_modifier(move_type: str, weather: str) -> float:
    w = normalize_id(weather or "")
    mt = normalize_id(move_type or "")
    if w in {"rain", "raindance", "rainy"}:
        if mt == "water":
            return 1.5
        if mt == "fire":
            return 0.5
    if w in {"sun", "sunnyday", "harshsunlight"}:
        if mt == "fire":
            return 1.5
        if mt == "water":
            return 0.5
    return 1.0


def _infer_damage_stats(move_category: str):
    cat = normalize_id(move_category)
    if cat == "physical":
        return "atk", "def"
    if cat == "special":
        return "spa", "spd"
    return None, None


def _build_stat_from_side(side: dict, label: str) -> dict:
    active_receipt = resolve_active_combatant(side) if side.get("pokemon") else {"status": "not_checked"}
    if "final_stats" in side:
        fs = side["final_stats"]
        try:
            stats = {k: int(fs[k]) for k in STAT_KEYS}
        except Exception as e:
            return {"entity": f"{label}_displayed_stats", "status": "fail", "reason": f"invalid final_stats: {e}"}
        if active_receipt.get("status") != "pass":
            return {"entity": f"{label}_displayed_stats", "status": "fail", "reason": "active-form gate failed for provided final_stats", "active_form_receipt": active_receipt}
        return {
            "entity": f"{label}_displayed_stats",
            "pokemon": side.get("pokemon", "provided_final_stats"),
            "pokemon_id": active_receipt.get("active_form_id", side.get("pokemon", "")),
            "pokemon_name": active_receipt.get("active_form", {}).get("name", side.get("pokemon", "")),
            "team_form_id": active_receipt.get("team_form_id"),
            "active_form_id": active_receipt.get("active_form_id"),
            "stat_source": active_receipt.get("stat_source"),
            "display_name": active_receipt.get("display_name", side.get("pokemon", "provided_final_stats")),
            "displayed_stats": stats,
            "source": "provided final_stats in scenario + active-form receipt",
            "active_form_receipt": active_receipt,
            "status": "pass",
        }
    return verify_stat(side.get("pokemon", ""), side.get("nature", ""), side.get("spread"), side)


def _supported_item_damage_modifier(item_receipt: dict, move_type: str, type_multiplier: float, board: dict) -> tuple[float, list]:
    """Return supported local item modifier and notes.

    This intentionally supports only a small, explicit list. Unknown boosting item
    effects require an explicit numeric scenario modifier; they are not inferred from prose.
    """
    notes = []
    if not item_receipt or item_receipt.get("status") != "pass":
        return 1.0, notes
    iid = normalize_id(item_receipt.get("id", ""))
    mtype = normalize_id(move_type)
    type_items = {
        "blackbelt": "fighting", "blackglasses": "dark", "charcoal": "fire", "dragonfang": "dragon",
        "fairyfeather": "fairy", "hardstone": "rock", "magnet": "electric", "metalcoat": "steel",
        "miracleseed": "grass", "mysticwater": "water", "nevermeltice": "ice", "poisonbarb": "poison",
        "sharpbeak": "flying", "silkscarf": "normal", "silverpowder": "bug", "softsand": "ground",
        "spelltag": "ghost", "twistedspoon": "psychic",
    }
    if iid == "lifeorb":
        notes.append("Life Orb local item exists and is implemented as 1.3x move power in this verifier; recoil is reported but not subtracted from damage output.")
        return 1.3, notes
    if iid in type_items and type_items[iid] == mtype:
        notes.append(f"{item_receipt.get('name', iid)} boosts {move_type}-type moves; implemented as 1.2x in this verifier.")
        return 1.2, notes
    if iid == "expertbelt" and type_multiplier > 1.0:
        notes.append("Expert Belt boosts super-effective moves; implemented as 1.2x in this verifier.")
        return 1.2, notes
    return 1.0, notes


def verify_damage(scenario: dict) -> dict:
    """Board-aware single-hit damage receipt.

    Required scenario fields:
    {
      "attacker": {"pokemon": "Garchomp", "nature": "Adamant", "spread": {...}, "move": "Earthquake", "item": "Life Orb"},
      "defender": {"pokemon": "Archaludon", "nature": "Modest", "spread": {...}, "ability": "Stamina"},
      "board": {"level": 50, "weather": "none", "spread_move": true/false, "target_count": 1/2, "attacker_stages": {}, "defender_stages": {}}
    }
    """
    attacker = scenario.get("attacker", {})
    defender = scenario.get("defender", {})
    board = scenario.get("board", {}) or {}
    level = int(board.get("level", scenario.get("level", 50)))
    out = {"mode": "damage_verification", "status": "fail", "scenario": scenario}

    atk_stat_receipt = _build_stat_from_side(attacker, "attacker")
    def_stat_receipt = _build_stat_from_side(defender, "defender")
    out["attacker_stat_receipt"] = atk_stat_receipt
    out["defender_stat_receipt"] = def_stat_receipt
    if atk_stat_receipt.get("status") != "pass" or def_stat_receipt.get("status") != "pass":
        out["reason"] = "attacker or defender displayed stat receipt failed"
        return out

    attacker_active_id = atk_stat_receipt.get("active_form_id") or atk_stat_receipt.get("pokemon_id") or attacker.get("pokemon", "")
    defender_active_id = def_stat_receipt.get("active_form_id") or def_stat_receipt.get("pokemon_id") or defender.get("pokemon", "")
    move_receipt = verify_move_on_pokemon(attacker_active_id, attacker.get("move", ""))
    out["move_receipt"] = move_receipt
    if move_receipt.get("status") != "pass":
        out["reason"] = "attacker move gate failed"
        return out
    category = move_receipt.get("category", "")
    atk_key, def_key = _infer_damage_stats(category)
    if atk_key is None:
        out["reason"] = "move is not Physical/Special damage or category is unknown; use mechanics-only mode"
        return out
    try:
        power = int(float(attacker.get("power", move_receipt.get("power", 0))))
    except Exception:
        power = 0
    if power <= 0:
        out["reason"] = "move power missing/zero/variable; exact damage cannot be calculated without resolved power"
        return out

    move_type = move_receipt.get("type", "")
    type_receipt = verify_type_effectiveness(move_type, defender_active_id)
    out["type_receipt"] = type_receipt
    out["typechart_receipt"] = type_receipt
    if type_receipt.get("status") != "pass":
        out["reason"] = "type effectiveness receipt failed"
        return out
    type_multiplier = float(type_receipt.get("total_type_multiplier", 1.0))
    if type_multiplier == 0.0:
        out.update({
            "status": "pass",
            "damage_rolls": [0]*16,
            "damage_percent": [0.0, 0.0],
            "ko_result": "NO_DAMAGE_TYPE_IMMUNITY",
            "rule": "Type multiplier is 0.0; do not force minimum 1 damage unless a verified exception exists.",
        })
        return out

    atk_raw = atk_stat_receipt["displayed_stats"][atk_key]
    def_raw = def_stat_receipt["displayed_stats"][def_key]
    atk_stage = (board.get("attacker_stages", {}) or {}).get(atk_key, attacker.get("stage", 0))
    def_stage = (board.get("defender_stages", {}) or {}).get(def_key, defender.get("stage", 0))
    atk_eff = math.floor(atk_raw * _stat_stage_multiplier(atk_stage))
    def_eff = max(1, math.floor(def_raw * _stat_stage_multiplier(def_stage)))

    attacker_types = _get_types_for_pokemon(attacker_active_id)
    stab = 1.5 if normalize_id(move_type) in attacker_types else 1.0
    weather = _weather_modifier(move_type, board.get("weather", "none"))
    spread_mod = 0.75 if (bool(board.get("spread_move", False)) or int(board.get("target_count", 1) or 1) > 1) else 1.0
    screen_mod = float(board.get("screen_modifier", 1.0))
    burn_mod = 0.5 if (normalize_id(category) == "physical" and bool(attacker.get("burned", False)) and not bool(board.get("ignore_burn", False))) else 1.0

    item_receipt = None
    item_mod = 1.0
    item_notes = []
    if attacker.get("item"):
        item_receipt = verify_item(attacker.get("item"))
        out["attacker_item_receipt"] = item_receipt
        if item_receipt.get("status") != "pass":
            out["reason"] = "attacker item was provided but item gate failed"
            return out
        item_mod, item_notes = _supported_item_damage_modifier(item_receipt, move_type, type_multiplier, board)

    explicit_mod = float(board.get("extra_modifier", scenario.get("extra_modifier", 1.0)))
    modifier_without_random = stab * type_multiplier * weather * spread_mod * screen_mod * burn_mod * item_mod * explicit_mod
    base = math.floor(math.floor(math.floor((math.floor((2 * level) / 5) + 2) * power * atk_eff / def_eff) / 50) + 2)
    rolls = [max(1, math.floor(base * modifier_without_random * r / 100)) for r in range(85, 101)]
    hp = int(def_stat_receipt["displayed_stats"]["hp"])
    min_pct = rolls[0] / hp * 100
    max_pct = rolls[-1] / hp * 100
    ohko_count = sum(1 for d in rolls if d >= hp)
    if ohko_count == 16:
        ko_result = "GUARANTEED_OHKO"
    elif ohko_count == 0:
        ko_result = "SURVIVES_ONE_HIT_16_OF_16"
    else:
        ko_result = f"OHKO_CHANCE_{ohko_count}_OF_16"
    out.update({
        "status": "pass",
        "level": level,
        "active_form_receipts": {"attacker": atk_stat_receipt.get("active_form_receipt"), "defender": def_stat_receipt.get("active_form_receipt")},
        "stat_used": {"attacker": atk_key, "defender": def_key, "attacker_raw": atk_raw, "defender_raw": def_raw, "attacker_effective": atk_eff, "defender_effective": def_eff, "attacker_stage": int(atk_stage), "defender_stage": int(def_stage)},
        "base_power": power,
        "base_damage_before_modifier": base,
        "modifier_stack": {
            "stab": stab,
            "type": type_multiplier,
            "weather": weather,
            "spread": spread_mod,
            "screen": screen_mod,
            "burn": burn_mod,
            "item": item_mod,
            "extra": explicit_mod,
            "modifier_without_random": modifier_without_random,
        },
        "item_notes": item_notes,
        "damage_rolls": rolls,
        "damage_percent": [round(min_pct, 1), round(max_pct, 1)],
        "defender_hp": hp,
        "ohko_rolls": ohko_count,
        "ko_result": ko_result,
        "source": "verify.py damage + local 01/05-07/08/typechart + 09 damage formula",
        "rule": "No damage receipt = no KO/survival claim. This receipt uses 16 rolls from 85 to 100.",
    })
    return out


def verify_sequence(scenario: dict) -> dict:
    """Stateful repeated-hit sequence receipt for on-hit effects such as Stamina.

    Uses verify_damage for each hit, then applies locally locked Stamina timing:
    hit 1 uses current Defense stage; if the defender is hit by a Physical damaging move
    and has Stamina, Defense +1 applies only after that hit for later hits.
    """
    hits = int(scenario.get("hits", scenario.get("turns", 2)))
    defender = scenario.get("defender", {})
    ability = normalize_id(defender.get("ability", ""))
    current_hp = None
    current_def_stage = int(((scenario.get("board", {}) or {}).get("defender_stages", {}) or {}).get("def", defender.get("def_stage", 0)))
    out_hits = []
    remaining_hp = None
    for i in range(1, hits + 1):
        sc = json.loads(json.dumps(scenario))
        sc.setdefault("board", {}).setdefault("defender_stages", {})["def"] = current_def_stage
        dmg = verify_damage(sc)
        if dmg.get("status") != "pass":
            return {"mode": "stateful_sequence_verification", "status": "fail", "reason": f"damage receipt failed at hit {i}", "failed_receipt": dmg, "hits": out_hits}
        if current_hp is None:
            current_hp = int(dmg["defender_hp"])
            remaining_hp = current_hp
        roll_min = dmg["damage_rolls"][0]
        roll_max = dmg["damage_rolls"][-1]
        remaining_hp_after_min = remaining_hp - roll_min
        remaining_hp_after_max = remaining_hp - roll_max
        move_category = normalize_id(dmg.get("move_receipt", {}).get("category", ""))
        stamina_applied_after_hit = ability == "stamina" and move_category == "physical" and roll_min > 0
        hit_record = {
            "hit": i,
            "def_stage_used": current_def_stage,
            "damage_rolls": dmg["damage_rolls"],
            "damage_percent": dmg["damage_percent"],
            "remaining_hp_range_after_hit": [remaining_hp_after_max, remaining_hp_after_min],
            "stamina_applied_after_hit": stamina_applied_after_hit,
            "rule": "Stamina, if triggered, applies after the damage of this hit; it does not reduce this same hit retroactively.",
        }
        if remaining_hp_after_min <= 0:
            hit_record["sequence_stops_after_hit"] = True
            hit_record["stop_reason"] = "minimum roll already KOs; later hits do not occur in this line"
            out_hits.append(hit_record)
            remaining_hp = remaining_hp_after_min
            break
        out_hits.append(hit_record)
        remaining_hp = remaining_hp_after_min
        if stamina_applied_after_hit:
            current_def_stage = min(6, current_def_stage + 1)
    possible_faint_by_min_line = any(h["remaining_hp_range_after_hit"][1] <= 0 for h in out_hits)
    guaranteed_faint_by_max_line = any(h["remaining_hp_range_after_hit"][0] <= 0 for h in out_hits)
    return {
        "mode": "stateful_sequence_verification",
        "status": "pass",
        "hits_requested": hits,
        "defender_ability": defender.get("ability", ""),
        "hits": out_hits,
        "possible_faint_in_sequence": possible_faint_by_min_line,
        "guaranteed_faint_under_max_rolls": guaranteed_faint_by_max_line,
        "source": "verify.py sequence + verify.py damage",
        "rule": "No sequence receipt = no Stamina / staged-hit claim.",
    }

def verify_set(set_object: dict) -> dict:
    """Verify one Pokémon set object.

    Required for final-team payloads:
    {
      "pokemon": "Kingambit",
      "ability": "Defiant",
      "item": "Leftovers",
      "nature": "Adamant",
      "spread": {"hp":28,"atk":20,"def":8,"spa":0,"spd":4,"spe":6},
      "moves": ["Sucker Punch", "Iron Head", "Protect", "Kowtow Cleave"]
    }
    """
    pkmn_receipt = verify_pokemon(set_object.get("pokemon", ""))
    out = {"mode": "team_set_verification", "input": set_object, "pokemon_gate": pkmn_receipt}

    if pkmn_receipt["status"] != "pass":
        out["active_form"] = {"status": "fail", "reason": "pokemon gate failed before active-form resolution"}
        out["set_ok"] = False
        return out

    active_receipt = resolve_active_combatant(set_object)
    out["active_form"] = active_receipt
    if active_receipt.get("status") != "pass":
        out["ability"] = {"status": "fail", "reason": "active-form gate failed"}
        out["item"] = verify_item(set_object.get("item", "")) if set_object.get("item") else {"status": "fail", "reason": "missing item"}
        out["moves"] = []
        out["set_ok"] = False
        return out

    pid = active_receipt.get("active_form_id", pkmn_receipt["id"])
    out["ability"] = active_receipt.get("battle_ability_receipt", verify_ability_on_pokemon(pid, set_object.get("ability", "")))
    out["item"] = verify_item(set_object.get("item", ""))
    out["moves"] = [verify_move_on_pokemon(pid, m) for m in set_object.get("moves", [])]

    spread_input = (
        set_object.get("spread")
        if "spread" in set_object
        else set_object.get("investments", set_object.get("stat_plan", None))
    )
    out["spread"] = verify_spread(spread_input)
    spread_present = any(k in set_object for k in ["spread", "investments", "stat_plan"])
    spread_required = bool(set_object.get("spread_required", False) or spread_present)
    out["spread_required"] = spread_required
    spread_ok = (not spread_required) or out["spread"]["status"] == "pass"

    nature = set_object.get("nature", "")
    stat_required = bool(set_object.get("stat_required", spread_required))
    out["stat_required"] = stat_required
    if spread_ok and nature and out["spread"].get("status") == "pass":
        out["displayed_stats"] = verify_stat(set_object.get("pokemon", pid), nature, out["spread"]["spread"], set_object)
    elif stat_required:
        out["displayed_stats"] = {
            "entity": "displayed_stats",
            "status": "fail",
            "reason": "nature + valid spread are required for final displayed stat receipt",
            "nature_query": nature,
        }
    else:
        out["displayed_stats"] = {"entity": "displayed_stats", "status": "not_required"}
    stat_ok = (not stat_required) or out["displayed_stats"].get("status") == "pass"

    all_pass = (
        out["ability"]["status"] == "pass"
        and out["item"]["status"] == "pass"
        and len(out["moves"]) == 4
        and all(m["status"] == "pass" for m in out["moves"])
        and spread_ok
        and stat_ok
    )
    out["set_ok"] = all_pass
    return out



CHOICE_ITEM_IDS = {"choicescarf", "choiceband", "choicespecs"}



PROVENANCE_LABELS = {
    "META_DIRECT": "Exact Pokémon/item/move/set source from an approved Champions 2v2 meta source.",
    "META_PATTERN": "Meta role/core pattern found, but not an exact set receipt for this slot.",
    "META_SPREAD_DIRECT": "Exact Pokémon nature+spread from an approved Champions spread table or usage source.",
    "TOURNAMENT_LIST_DIRECT": "Exact set/spread from a tournament teamlist or replay-backed list.",
    "LOCAL_TEAM_FIT": "Assistant/team-fit choice after local legality and compatibility verification; not sold as meta-direct.",
    "LOCAL_BENCHMARK_OVERRIDE": "Changed from meta baseline only after speed/damage benchmark receipt justifies it.",
    "LOCAL_GUESS": "No meta spread and no benchmark; audit-only unless clearly labelled as uncertain.",
    "ITEM_CLAUSE_REPAIR": "Changed because Item Clause or team item economy required a different verified item.",
    "SPEED_MODE_FIT": "Chosen to fit the team's Tailwind/TR/weather/priority speed plan.",
    "DAMAGE_BENCHMARK": "Chosen because verify.py damage/stat benchmark supports the role.",
    "USER_REQUESTED": "User explicitly requested this choice.",
    "EXPERIMENTAL": "Experimental local choice; should not be presented as established meta.",
}

HARD_PROVENANCE_LABELS = set(PROVENANCE_LABELS)

SPEED_ROLE_LABELS = {
    "FAST_MODE_SWEEPER", "TR_SWEEPER", "BRIDGE_SPEED", "BULKY_PIVOT",
    "PRIORITY_CLEANER", "SUPPORT", "WEATHER_SPEED", "SETUP_ATTACKER", "LOCAL_TEAM_FIT",
}


def _get_provenance(set_object: dict, kind: str) -> str:
    prov = set_object.get("provenance", {}) if isinstance(set_object.get("provenance", {}), dict) else {}
    if kind == "item":
        raw = set_object.get("item_source") or set_object.get("item_provenance") or prov.get("item") or prov.get("item_source") or ""
    elif kind == "spread":
        raw = set_object.get("spread_source") or set_object.get("spread_provenance") or prov.get("spread") or prov.get("spread_source") or ""
    else:
        raw = set_object.get("moves_source") or set_object.get("move_provenance") or prov.get("moves") or prov.get("moves_source") or ""
    compact = normalize_id(str(raw)).upper()
    for known in HARD_PROVENANCE_LABELS:
        if normalize_id(known).upper() == compact:
            return known
    return str(raw or "").strip()


def _set_speed_role(set_object: dict, set_receipt: dict, team_speed_modes: list[str]) -> str:
    raw = set_object.get("speed_role") or set_object.get("speed_archetype") or set_object.get("team_role") or ""
    label = str(raw).strip().upper().replace(" ", "_").replace("-", "_")
    if label in SPEED_ROLE_LABELS:
        return label
    move_ids = {normalize_id(m.get("move_id", m.get("move_query", ""))) for m in set_receipt.get("moves", [])}
    spread = set_receipt.get("spread", {}).get("spread", {}) or {}
    spe_inv = int(spread.get("spe", 0) or 0) if isinstance(spread, dict) else 0
    active = set_receipt.get("active_form", {}).get("active_form", set_receipt.get("pokemon_gate", {}))
    try:
        base_spe = int(active.get("stats", {}).get("spe", 0))
    except Exception:
        base_spe = 0
    if "tailwind" in move_ids or "trickroom" in move_ids or "ragepowder" in move_ids or "followme" in move_ids:
        return "SUPPORT"
    if "trick_room" in team_speed_modes and spe_inv <= 6:
        return "TR_SWEEPER" if base_spe and base_spe <= 80 else "BULKY_PIVOT"
    if "tailwind" in team_speed_modes and "trick_room" in team_speed_modes and 7 <= spe_inv <= 24:
        return "BRIDGE_SPEED"
    if spe_inv >= 24:
        return "FAST_MODE_SWEEPER"
    if any(mid in {"suckerpunch", "aquajet", "bulletpunch", "shadowsneak", "quickattack", "iceshard", "machpunch"} for mid in move_ids):
        return "PRIORITY_CLEANER"
    return "LOCAL_TEAM_FIT"


def _detect_team_speed_modes(team_receipt: dict) -> list[str]:
    move_ids = {normalize_id(m.get("move_id", m.get("move_query", ""))) for r in team_receipt.get("sets", []) for m in r.get("moves", [])}
    modes = []
    if "tailwind" in move_ids:
        modes.append("tailwind")
    if "trickroom" in move_ids:
        modes.append("trick_room")
    ability_ids = {normalize_id(r.get("ability", {}).get("ability_name", "")) for r in team_receipt.get("sets", [])}
    if ability_ids & {"swiftswim", "chlorophyll", "sandrush", "slushrush"}:
        modes.append("weather_speed")
    if not modes:
        modes.append("none")
    return modes



META_SPREAD_DIRECT_LABELS = {"META_DIRECT", "META_SPREAD_DIRECT", "TOURNAMENT_LIST_DIRECT"}
LOCAL_OVERRIDE_LABELS = {"LOCAL_TEAM_FIT", "SPEED_MODE_FIT", "LOCAL_BENCHMARK_OVERRIDE", "DAMAGE_BENCHMARK", "EXPERIMENTAL", "LOCAL_GUESS"}
WEATHER_SPEED_ABILITIES = {"sandrush", "swiftswim", "chlorophyll", "slushrush"}


def _norm_pokemon_key(name: str) -> str:
    return normalize_id(str(name or "").replace("Mega ", ""))


def _normalize_meta_spread_record(rec, default_pokemon="") -> dict | None:
    """Normalize flexible meta spread input into a compact receipt.

    Accepted fields: pokemon/name, nature, spread (dict/list/slash string), source,
    usage, label/source_label. This is intentionally small: it verifies format,
    not the web source itself.
    """
    if not isinstance(rec, dict):
        return None
    spread_raw = rec.get("spread") or rec.get("investment") or rec.get("stat_plan")
    if not spread_raw and all(k in rec for k in STAT_KEYS):
        spread_raw = {k: rec[k] for k in STAT_KEYS}
    spread, note = _coerce_spread(spread_raw)
    if spread is None:
        return {"status": "fail", "reason": f"invalid meta spread: {note}", "input": rec}
    label = rec.get("source_label") or rec.get("provenance") or rec.get("label") or "META_SPREAD_DIRECT"
    label_norm = _get_known_label(label, default="META_SPREAD_DIRECT")
    return {
        "status": "pass",
        "pokemon": rec.get("pokemon") or rec.get("name") or default_pokemon,
        "nature": str(rec.get("nature") or "").strip(),
        "spread": spread,
        "spread_display": _spread_display_fields(spread),
        "source": rec.get("source") or rec.get("url") or rec.get("source_name") or "meta spread source",
        "usage": rec.get("usage") or rec.get("usage_percent") or rec.get("percent") or "",
        "source_label": label_norm,
        "note": rec.get("note") or rec.get("reason") or "",
    }


def _get_known_label(raw, default="") -> str:
    compact = normalize_id(str(raw or "")).upper()
    for known in HARD_PROVENANCE_LABELS:
        if normalize_id(known).upper() == compact:
            return known
    return default or str(raw or "").strip()


def _collect_meta_spread_index(team_payload_or_receipt=None, external_meta_spreads=None) -> dict:
    """Build pokemon_id -> [meta spread records] from external file and team payload."""
    records = []
    srcs = []
    if external_meta_spreads:
        srcs.append(external_meta_spreads)
    if isinstance(team_payload_or_receipt, dict):
        srcs.append(team_payload_or_receipt.get("meta_spreads"))
        srcs.append(team_payload_or_receipt.get("meta_spread_baselines"))
        if "team" in team_payload_or_receipt:
            for slot in team_payload_or_receipt.get("team") or []:
                if isinstance(slot, dict):
                    rec = slot.get("meta_spread") or slot.get("meta_baseline") or slot.get("meta_spread_baseline")
                    if rec:
                        if isinstance(rec, dict) and not rec.get("pokemon"):
                            rec = dict(rec); rec["pokemon"] = slot.get("pokemon", "")
                        records.append(rec)
    for src in srcs:
        if isinstance(src, dict):
            if "records" in src:
                records.extend(src.get("records") or [])
            elif "spreads" in src:
                records.extend(src.get("spreads") or [])
            else:
                # Mapping: {"excadrill": {...} or [{...}]}
                for k, v in src.items():
                    vals = v if isinstance(v, list) else [v]
                    for rec in vals:
                        if isinstance(rec, dict):
                            rec = dict(rec); rec.setdefault("pokemon", k)
                        records.append(rec)
        elif isinstance(src, list):
            records.extend(src)
    idx = {}
    for rec in records:
        norm = _normalize_meta_spread_record(rec)
        if not norm or norm.get("status") != "pass":
            continue
        key = _norm_pokemon_key(norm.get("pokemon"))
        if key:
            idx.setdefault(key, []).append(norm)
    return idx


def _slot_meta_spread(inp: dict, external_index: dict) -> dict | None:
    direct = inp.get("meta_spread") or inp.get("meta_baseline") or inp.get("meta_spread_baseline")
    if direct:
        if isinstance(direct, dict) and not direct.get("pokemon"):
            direct = dict(direct); direct["pokemon"] = inp.get("pokemon", "")
        rec = _normalize_meta_spread_record(direct, inp.get("pokemon", ""))
        if rec and rec.get("status") == "pass":
            return rec
    key = _norm_pokemon_key(inp.get("pokemon"))
    candidates = external_index.get(key) or []
    return candidates[0] if candidates else None


def _has_benchmark(inp: dict, kind: str = "any") -> bool:
    fields = [
        inp.get("benchmark"), inp.get("benchmarks"), inp.get("benchmark_receipts"),
        inp.get("speed_benchmark"), inp.get("speed_benchmarks"),
        inp.get("damage_benchmark"), inp.get("damage_benchmarks"),
        inp.get("spread_benchmark"), inp.get("spread_benchmarks"),
    ]
    if kind == "speed":
        fields = [inp.get("speed_benchmark"), inp.get("speed_benchmarks"), inp.get("benchmarks"), inp.get("benchmark_receipts")]
    if kind == "damage":
        fields = [inp.get("damage_benchmark"), inp.get("damage_benchmarks"), inp.get("benchmarks"), inp.get("benchmark_receipts")]
    return any(bool(x) for x in fields)


def _ability_weather_speed_multiplier(set_receipt: dict) -> int:
    ability_id = normalize_id(set_receipt.get("ability", {}).get("ability_name", ""))
    return 2 if ability_id in WEATHER_SPEED_ABILITIES else 1


def _spread_diff(meta_spread: dict, proposed_spread: dict) -> dict:
    return {k: int(proposed_spread.get(k, 0) or 0) - int(meta_spread.get(k, 0) or 0) for k in STAT_KEYS}


def evaluate_spread_fit(team_receipt: dict, meta_spreads=None) -> dict:
    """v29.24: meta spread baseline first; team-fit overrides need benchmarks.

    This gate does not search the web. The assistant must pass any live meta
    spread/table data into `meta_spread` on each slot or `meta_spreads` in the
    team payload. The gate then compares final spread to that baseline.
    """
    payload = team_receipt.get("input_payload") if isinstance(team_receipt, dict) else None
    external_index = _collect_meta_spread_index(payload, meta_spreads)
    out = {
        "entity": "spread_fit_receipt",
        "status": "pass",
        "slots": [],
        "failures": [],
        "warnings": [],
        "rule": "Use meta spread as baseline when available. Override only with speed/damage benchmark receipt; otherwise stay close to meta.",
    }
    for r in team_receipt.get("sets", []):
        inp = r.get("input", {}) or {}
        pokemon = r.get("active_form", {}).get("display_name", r.get("pokemon_gate", {}).get("name", inp.get("pokemon", "unknown")))
        proposed = r.get("spread", {}).get("spread", {}) or {}
        proposed_display = _spread_display_fields(proposed)
        spread_label = _get_provenance(inp, "spread")
        meta = _slot_meta_spread(inp, external_index)
        slot = {
            "slot": r.get("slot"),
            "pokemon": pokemon,
            "final_source": spread_label,
            "proposed": {"nature": inp.get("nature", ""), "spread": proposed, "display": proposed_display},
            "status": "pass",
            "decision": "NO_META_BASELINE",
            "warnings": [],
        }
        if not meta:
            if spread_label in {"LOCAL_GUESS", "LOCAL_TEAM_FIT", "EXPERIMENTAL"}:
                warn = {"code": "WARN_NO_META_SPREAD_BASELINE", "pokemon": pokemon, "detail": "No Pokémon-specific meta spread baseline was supplied; local spread must be labelled and should avoid strong meta claims."}
                slot["warnings"].append(warn); out["warnings"].append(warn)
            out["slots"].append(slot)
            continue
        meta_nature = meta.get("nature") or inp.get("nature", "")
        meta_spread = meta.get("spread", {})
        diff = _spread_diff(meta_spread, proposed)
        exact = all(v == 0 for v in diff.values()) and normalize_id(meta_nature) == normalize_id(inp.get("nature", meta_nature))
        speed_bench = _has_benchmark(inp, "speed")
        damage_bench = _has_benchmark(inp, "damage")
        any_bench = _has_benchmark(inp, "any") or spread_label in {"LOCAL_BENCHMARK_OVERRIDE", "DAMAGE_BENCHMARK"}
        meta_stat = verify_stat(inp.get("pokemon", pokemon), meta_nature, meta_spread, inp)
        proposed_stat = r.get("displayed_stats", {})
        mult = _ability_weather_speed_multiplier(r)
        meta_spe = (meta_stat.get("displayed_stats", {}) or {}).get("spe")
        prop_spe = (proposed_stat.get("displayed_stats", {}) or {}).get("spe")
        slot.update({
            "meta_baseline": meta,
            "diff": diff,
            "speed_tradeoff": {
                "weather_speed_multiplier": mult,
                "meta_spe": meta_spe,
                "proposed_spe": prop_spe,
                "meta_effective_spe": meta_spe * mult if isinstance(meta_spe, int) else None,
                "proposed_effective_spe": prop_spe * mult if isinstance(prop_spe, int) else None,
            },
            "benchmark_receipt_present": bool(any_bench),
            "speed_benchmark_present": bool(speed_bench),
            "damage_benchmark_present": bool(damage_bench),
        })
        if exact:
            slot["decision"] = "USE_META_BASELINE"
        else:
            slot["decision"] = "CHECK_OVERRIDE"
            speed_drop = diff.get("spe", 0) < 0
            large_speed_drop = diff.get("spe", 0) <= -8
            bulk_gain = sum(max(0, diff.get(k, 0)) for k in ("hp", "def", "spd"))
            if spread_label in META_SPREAD_DIRECT_LABELS:
                warn = {"code": "WARN_META_LABEL_BUT_SPREAD_DIFFERS", "pokemon": pokemon, "detail": "Spread is labelled meta-direct but differs from supplied meta baseline; verify the source or relabel as benchmark override."}
                slot["warnings"].append(warn); out["warnings"].append(warn)
            if spread_label == "LOCAL_GUESS":
                fail = {"code": "FAIL_LOCAL_GUESS_OVERRIDES_META_SPREAD", "pokemon": pokemon, "detail": "LOCAL_GUESS cannot override a supplied meta spread baseline."}
                slot["status"] = "fail"; out["failures"].append(fail)
            if large_speed_drop and not speed_bench:
                fail = {"code": "FAIL_SPEED_DROP_FROM_META_WITHOUT_BENCHMARK", "pokemon": pokemon, "detail": "Final spread lowers Speed from meta baseline by 8+ points without speed benchmark receipt."}
                slot["status"] = "fail"; out["failures"].append(fail)
            elif speed_drop and not speed_bench:
                warn = {"code": "WARN_SPEED_DROP_FROM_META_WITHOUT_BENCHMARK", "pokemon": pokemon, "detail": "Speed is lower than meta baseline; add a speed benchmark or stay with meta spread."}
                slot["warnings"].append(warn); out["warnings"].append(warn)
            if bulk_gain >= 16 and not damage_bench:
                fail = {"code": "FAIL_BULK_DUMP_FROM_META_WITHOUT_DAMAGE_BENCHMARK", "pokemon": pokemon, "detail": "Bulk investment gained from changing meta spread lacks damage/survival benchmark."}
                slot["status"] = "fail"; out["failures"].append(fail)
            if slot["status"] != "fail":
                slot["decision"] = "ACCEPT_OVERRIDE" if any_bench else "WARN_OVERRIDE_NO_BENCHMARK"
        out["slots"].append(slot)
    if out["failures"]:
        out["status"] = "fail"
    elif out["warnings"]:
        out["status"] = "pass_with_warnings"
    return out



# ---------------------------------------------------------------------------
# v29.37: item-spread coherence / reason receipt gate
# ---------------------------------------------------------------------------

REASON_SOURCE_LABELS = {
    "META_DIRECT", "META_SPREAD_DIRECT", "TOURNAMENT_LIST_DIRECT",
    "LOCAL_MECHANIC_RECEIPT", "DAMAGE_BENCHMARK", "SPEED_BENCHMARK",
    "ITEM_SPREAD_COHERENCE", "USER_CORRECTION", "USER_REQUESTED",
    "LOCAL_FALLBACK", "LOCAL_TEAM_FIT", "EXPERIMENTAL",
}

SURVIVAL_REASON_PATTERN = re.compile(r"(?i)(surviv|live\b|tank|avoid\s+KO|endure|รอด|ทน|รับ(?:ท่า|ดาเมจ)?|ไม่ตาย|กันตาย|ช่วย(?:ให้)?รอด|Electric|Thunderbolt|ฟ้า|ไฟฟ้า)")
WEATHER_REASON_PATTERN = re.compile(r"(?i)(Drizzle|rain|ฝน|Weather\s+Ball|Hurricane|Sand\s+Rush|Swift\s+Swim|Chlorophyll|Slush\s+Rush|weather|terrain|Sandstorm|Snow|หิมะ|พายุทราย)")


def _get_reason_source(set_object: dict, kind: str = "spread") -> str:
    prov = set_object.get("provenance", {}) if isinstance(set_object.get("provenance", {}), dict) else {}
    raw = (
        set_object.get(f"{kind}_reason_source")
        or set_object.get("reason_source")
        or prov.get(f"{kind}_reason_source")
        or prov.get("reason_source")
        or ""
    )
    compact = normalize_id(str(raw)).upper()
    for known in REASON_SOURCE_LABELS:
        if normalize_id(known).upper() == compact:
            return known
    return str(raw or "").strip()


def _reason_text_from_set(set_object: dict) -> str:
    parts = []
    keys = [
        "reason", "notes", "note", "explanation", "why",
        "spread_reason", "item_reason", "role_reason", "teamfit_reason",
    ]
    for k in keys:
        v = set_object.get(k)
        if isinstance(v, list):
            parts.extend(str(x) for x in v)
        elif isinstance(v, dict):
            parts.extend(str(x) for x in v.values())
        elif v:
            parts.append(str(v))
    prov = set_object.get("provenance", {}) if isinstance(set_object.get("provenance", {}), dict) else {}
    for k in ["reason", "spread_reason", "item_reason"]:
        v = prov.get(k)
        if isinstance(v, list):
            parts.extend(str(x) for x in v)
        elif v:
            parts.append(str(v))
    return "\n".join(parts)


def _slot_damage_invest_target(set_receipt: dict) -> tuple[str, int, int]:
    """Return (preferred_stat, physical_count, special_count)."""
    physical = 0
    special = 0
    for m in set_receipt.get("moves", []) or []:
        cat = normalize_id(m.get("category", ""))
        if cat == "physical":
            physical += 1
        elif cat == "special":
            special += 1
    if special > physical:
        return "spa", physical, special
    if physical > special:
        return "atk", physical, special
    if special and physical:
        return "mixed", physical, special
    return "utility", physical, special


def evaluate_item_spread_coherence(team_receipt: dict) -> dict:
    """Cross-check item, spread, and written reason.

    This gate is intentionally small and receipt-driven. It does not ban bulk on
    Focus Sash, but it makes bulk/survival reasoning require meta spread evidence
    or damage/speed benchmark receipts.
    """
    out = {
        "entity": "item_spread_coherence_receipt",
        "status": "pass",
        "slots": [],
        "failures": [],
        "warnings": [],
        "rule": "Item, spread, and reason must agree. Focus Sash defaults to action value (Speed/damage/utility timing); bulky Sash spreads need meta or benchmark receipts.",
    }
    for r in team_receipt.get("sets", []) or []:
        inp = r.get("input", {}) or {}
        pokemon_name = r.get("active_form", {}).get("display_name", r.get("pokemon_gate", {}).get("name", inp.get("pokemon", "unknown")))
        item_name = r.get("item", {}).get("name", inp.get("item", ""))
        item_id = normalize_id(r.get("item", {}).get("id", inp.get("item", "")))
        item_label = _get_provenance(inp, "item")
        spread_label = _get_provenance(inp, "spread")
        reason_source = _get_reason_source(inp, "spread")
        reason_text = _reason_text_from_set(inp)
        spread = r.get("spread", {}).get("spread", {}) or {}
        hp = int(spread.get("hp", 0) or 0) if isinstance(spread, dict) else 0
        atk = int(spread.get("atk", 0) or 0) if isinstance(spread, dict) else 0
        dfv = int(spread.get("def", 0) or 0) if isinstance(spread, dict) else 0
        spa = int(spread.get("spa", 0) or 0) if isinstance(spread, dict) else 0
        spd = int(spread.get("spd", 0) or 0) if isinstance(spread, dict) else 0
        spe = int(spread.get("spe", 0) or 0) if isinstance(spread, dict) else 0
        bulk_sum = hp + dfv + spd
        bulk_heavy = max(hp, dfv, spd) >= 24 or bulk_sum >= 32
        damage_bench = _has_benchmark(inp, "damage") or spread_label in {"DAMAGE_BENCHMARK", "LOCAL_BENCHMARK_OVERRIDE"} or reason_source in {"DAMAGE_BENCHMARK", "LOCAL_BENCHMARK_OVERRIDE"}
        speed_bench = _has_benchmark(inp, "speed") or spread_label in {"SPEED_MODE_FIT", "LOCAL_BENCHMARK_OVERRIDE"} or reason_source in {"SPEED_BENCHMARK", "LOCAL_BENCHMARK_OVERRIDE"}
        meta_supported = spread_label in META_SPREAD_DIRECT_LABELS or reason_source in {"META_DIRECT", "META_SPREAD_DIRECT", "TOURNAMENT_LIST_DIRECT"}
        user_supported = spread_label == "USER_REQUESTED" or reason_source == "USER_REQUESTED"
        preferred_stat, phys_count, spec_count = _slot_damage_invest_target(r)
        damage_inv = max(atk, spa) if preferred_stat == "mixed" else (atk if preferred_stat == "atk" else spa if preferred_stat == "spa" else 0)
        slot = {
            "slot": r.get("slot"),
            "pokemon": pokemon_name,
            "item": item_name,
            "item_source": item_label,
            "spread_source": spread_label,
            "reason_source": reason_source or "missing",
            "spread": {"hp": hp, "atk": atk, "def": dfv, "spa": spa, "spd": spd, "spe": spe},
            "bulk_investment": bulk_sum,
            "preferred_damage_stat": preferred_stat,
            "damage_investment": damage_inv,
            "speed_investment": spe,
            "status": "pass",
            "warnings": [],
        }
        if item_id == "focussash":
            slot["sash_policy"] = "Sash defaults to action value: Speed, damage, or utility timing. Bulk claims need meta or benchmark support."
            if bulk_heavy and not (meta_supported or damage_bench or user_supported):
                fail = {"code": "FAIL_SASH_BULK_WITHOUT_BENCHMARK", "pokemon": pokemon_name, "detail": "Focus Sash spread invests heavily into HP/Def/SpD but has no META_SPREAD_DIRECT/TOURNAMENT_LIST_DIRECT or damage/survival benchmark receipt."}
                slot["status"] = "fail"; out["failures"].append(fail)
            elif bulk_heavy and user_supported and not (meta_supported or damage_bench):
                warn = {"code": "WARN_USER_REQUESTED_SASH_BULK_NO_BENCHMARK", "pokemon": pokemon_name, "detail": "User requested or supplied a bulky Focus Sash spread, but no damage benchmark proves the bulk value."}
                slot["warnings"].append(warn); out["warnings"].append(warn)
            if SURVIVAL_REASON_PATTERN.search(reason_text or "") and not (meta_supported or damage_bench):
                fail = {"code": "FAIL_SURVIVAL_REASON_WITHOUT_DAMAGE_RECEIPT", "pokemon": pokemon_name, "detail": "Spread/item reason claims survival/tanking value without a damage or sequence receipt."}
                slot["status"] = "fail"; out["failures"].append(fail)
            if not bulk_heavy and spe >= 24 and (damage_inv >= 24 or preferred_stat == "utility"):
                slot["decision"] = "PASS_SASH_ACTION_VALUE"
            elif not bulk_heavy:
                warn = {"code": "WARN_SASH_ACTION_VALUE_WEAKLY_JUSTIFIED", "pokemon": pokemon_name, "detail": "Focus Sash spread is not bulky, but Speed/damage/utility timing should still be explained by meta, role, or benchmark."}
                slot["warnings"].append(warn); out["warnings"].append(warn)
        if WEATHER_REASON_PATTERN.search(reason_text or ""):
            verified = _collect_verified_entities_from_receipt(team_receipt or {})
            has_mech = bool(verified.get("interaction") or verified.get("boardscan") or verified.get("mechanic") or (team_receipt.get("team_gates", {}).get("typepassive") if isinstance(team_receipt.get("team_gates"), dict) else False))
            if not has_mech and reason_source not in {"LOCAL_MECHANIC_RECEIPT", "META_DIRECT", "TOURNAMENT_LIST_DIRECT"}:
                fail = {"code": "FAIL_WEATHER_MECHANIC_REASON_WITHOUT_RECEIPT", "pokemon": pokemon_name, "detail": "Reason uses weather/field/move interaction language without a local mechanic, interaction, boardscan, or typepassive receipt."}
                slot["status"] = "fail"; out["failures"].append(fail)
        out["slots"].append(slot)
    if out["failures"]:
        out["status"] = "fail"
    elif out["warnings"]:
        out["status"] = "pass_with_warnings"
    return out


def verify_itemspread(team_payload) -> dict:
    if isinstance(team_payload, dict) and team_payload.get("mode") == "full_team_verification":
        receipt = team_payload
    else:
        receipt = verify_team(team_payload)
    return evaluate_item_spread_coherence(receipt)

def verify_spreadfit(team_payload, meta_spreads=None) -> dict:
    if isinstance(team_payload, dict) and team_payload.get("mode") == "full_team_verification":
        receipt = team_payload
    else:
        receipt = verify_team(team_payload)
    return evaluate_spread_fit(receipt, meta_spreads)

def evaluate_team_fit(team_receipt: dict) -> dict:
    modes = _detect_team_speed_modes(team_receipt)
    dual_speed = "tailwind" in modes and "trick_room" in modes
    mode_explanation = ""
    if "tailwind" in modes and "trick_room" in modes:
        mode_explanation = "Dual speed mode: Tailwind and Trick Room are both present. Do not force every slot into full Speed; bridge/bulky roles need explicit speed reasoning."
    elif "tailwind" in modes:
        mode_explanation = "Tailwind mode: fast/offensive slots may invest Speed, but bulky setters still need role-fit justification."
    elif "trick_room" in modes:
        mode_explanation = "Trick Room mode: slower/bulkier spreads are usually preferred unless a slot is explicitly off-mode."
    else:
        mode_explanation = "No explicit speed-control mode detected; speed investment must be justified by local role or benchmarks."
    out = {"entity": "team_fit_receipt", "status": "pass", "team_speed_modes": modes, "team_mode_explanation": mode_explanation, "slots": [], "failures": [], "warnings": [], "rule": "Meta is the candidate pool; final item/spread must be locally legal, team-fit justified, and provenance-labeled."}
    for r in team_receipt.get("sets", []):
        inp = r.get("input", {}) or {}
        item_label = _get_provenance(inp, "item")
        spread_label = _get_provenance(inp, "spread")
        moves_label = _get_provenance(inp, "moves")
        pokemon_name = r.get("active_form", {}).get("display_name", r.get("pokemon_gate", {}).get("name", inp.get("pokemon", "unknown")))
        item_name = r.get("item", {}).get("name", inp.get("item", ""))
        item_id = normalize_id(r.get("item", {}).get("id", inp.get("item", "")))
        speed_role = _set_speed_role(inp, r, modes)
        spread = r.get("spread", {}).get("spread", {}) or {}
        spe_inv = int(spread.get("spe", 0) or 0) if isinstance(spread, dict) else 0
        move_ids = {normalize_id(m.get("move_id", m.get("move_query", ""))) for m in r.get("moves", [])}
        active = r.get("active_form", {}).get("active_form", r.get("pokemon_gate", {}))
        try:
            base_spe = int(active.get("stats", {}).get("spe", 0))
        except Exception:
            base_spe = 0
        mid_speed = 60 <= base_spe <= 100
        slot = {"slot": r.get("slot"), "pokemon": pokemon_name, "item": item_name, "speed_role": speed_role, "base_spe": base_spe, "spe_investment": spe_inv, "item_source": item_label, "spread_source": spread_label, "moves_source": moves_label, "status": "pass", "warnings": []}
        if item_label not in HARD_PROVENANCE_LABELS:
            slot["status"] = "fail"
            out["failures"].append({"code": "FAIL_ITEM_SOURCE_UNLABELED", "pokemon": pokemon_name, "detail": "item_source/item_provenance must be one of the approved provenance labels"})
        if spread_label not in HARD_PROVENANCE_LABELS:
            slot["status"] = "fail"
            out["failures"].append({"code": "FAIL_SPREAD_SOURCE_UNLABELED", "pokemon": pokemon_name, "detail": "spread_source/spread_provenance must be one of the approved provenance labels"})
        if item_label in {"LOCAL_TEAM_FIT", "SPEED_MODE_FIT", "ITEM_CLAUSE_REPAIR", "DAMAGE_BENCHMARK", "EXPERIMENTAL"}:
            slot["warnings"].append({"code": "INFO_ITEM_SELECTED_BY_TEAM_FIT", "detail": f"{item_name} is labeled {item_label}, not meta-direct."})
        if dual_speed and item_id == "choicescarf":
            warn = {"code": "WARN_CHOICE_SCARF_CONFLICTS_WITH_DUAL_SPEED_MODE", "pokemon": pokemon_name, "detail": "Dual Tailwind + Trick Room teams should justify Choice Scarf; it may over-commit this slot to fast mode."}
            slot["warnings"].append(warn); out["warnings"].append(warn)
        if "trick_room" in modes and spe_inv >= 28 and speed_role not in {"FAST_MODE_SWEEPER", "WEATHER_SPEED"}:
            warn = {"code": "WARN_FULL_SPEED_CONFLICTS_WITH_TR_MODE", "pokemon": pokemon_name, "detail": "High Speed investment on a team with Trick Room needs an explicit fast-mode role."}
            slot["warnings"].append(warn); out["warnings"].append(warn)
        if dual_speed and mid_speed and (spe_inv >= 28 or item_id == "choicescarf") and speed_role not in {"FAST_MODE_SWEEPER", "WEATHER_SPEED"}:
            warn = {"code": "WARN_BRIDGE_MON_OVERCOMMITTED_TO_FAST_MODE", "pokemon": pokemon_name, "detail": "Mid-speed Pokémon on dual-speed teams often work better as bridge/bulky slots unless a benchmark receipt justifies full fast mode."}
            slot["warnings"].append(warn); out["warnings"].append(warn)
        if item_id == "focussash" and item_label != "META_DIRECT":
            warn = {"code": "WARN_FOCUS_SASH_NOT_META_DIRECT", "pokemon": pokemon_name, "detail": "Focus Sash is legal, but this slot must not be presented as meta-direct unless a Pokémon-specific meta receipt exists."}
            slot["warnings"].append(warn); out["warnings"].append(warn)
        hp_inv = int(spread.get("hp", 0) or 0) if isinstance(spread, dict) else 0
        def_inv = int(spread.get("def", 0) or 0) if isinstance(spread, dict) else 0
        spd_inv = int(spread.get("spd", 0) or 0) if isinstance(spread, dict) else 0
        if item_id == "focussash" and (hp_inv >= 24 or def_inv >= 24 or spd_inv >= 24):
            warn = {"code": "WARN_FOCUS_SASH_ON_BULKY_SPREAD", "pokemon": pokemon_name, "detail": "Focus Sash on a bulky spread needs a stronger reason; Sash is usually best on frail guarantee-action slots."}
            slot["warnings"].append(warn); out["warnings"].append(warn)
        if item_id in CHOICE_ITEM_IDS and "protect" in move_ids:
            warn = {"code": "WARN_CHOICE_ITEM_WITH_PROTECT_TEAMFIT", "pokemon": pokemon_name, "detail": "Choice item + Protect is a team-fit warning even when legal."}
            slot["warnings"].append(warn); out["warnings"].append(warn)
        out["slots"].append(slot)
    if out["failures"]:
        out["status"] = "fail"
    elif out["warnings"]:
        out["status"] = "pass_with_warnings"
    return out


def verify_teamfit(team_payload) -> dict:
    if isinstance(team_payload, dict) and team_payload.get("mode") == "full_team_verification":
        receipt = team_payload
    else:
        receipt = verify_team(team_payload)
    return evaluate_team_fit(receipt)


def _slot_display_name_from_receipt(r: dict) -> str:
    return r.get("active_form", {}).get("display_name", r.get("pokemon_gate", {}).get("name", r.get("input", {}).get("pokemon", "unknown")))


def _slot_speed_from_receipt(r: dict) -> int:
    stats = r.get("displayed_stats", {}).get("displayed_stats", {}) or {}
    try:
        return int(stats.get("spe", 0) or 0)
    except Exception:
        return 0


def _slot_move_ids(r: dict) -> set[str]:
    return {normalize_id(m.get("move_id", m.get("move_query", ""))) for m in r.get("moves", [])}


def _slot_move_display_map(r: dict) -> dict:
    out = {}
    for m in r.get("moves", []):
        mid = normalize_id(m.get("move_id", m.get("move_query", "")))
        out[mid] = m.get("display") or (f"{m.get('emoji','')} {m.get('move_name', m.get('move_query', mid))}".strip())
    return out


def evaluate_speed_plan(team_receipt: dict) -> dict:
    """v29.38: summarize speed modes from receipts, not prose labels.

    This does not decide a matchup by itself. It forces public advice to compare
    actual Speed buckets before recommending Tailwind or Trick Room.
    """
    modes = _detect_team_speed_modes(team_receipt)
    slots = []
    fast_benefit = []
    tr_benefit = []
    tr_partial = []
    tr_hurts = []
    warnings = []
    for r in team_receipt.get("sets", []):
        name = _slot_display_name_from_receipt(r)
        spe = _slot_speed_from_receipt(r)
        moves = _slot_move_ids(r)
        tf_slots = {x.get("slot"): x for x in (team_receipt.get("team_gates", {}).get("team_fit", {}).get("slots", []) or [])}
        tf = tf_slots.get(r.get("slot"), {})
        role = tf.get("speed_role") or _set_speed_role(r.get("input", {}) or {}, r, modes)
        tailwind_speed = spe * 2 if spe else 0
        slot = {
            "slot": r.get("slot"),
            "pokemon": name,
            "speed": spe,
            "tailwind_speed": tailwind_speed,
            "speed_role": role,
            "sets_tailwind": "tailwind" in moves,
            "sets_trick_room": "trickroom" in moves,
        }
        if spe >= 120 or role in {"FAST_MODE_SWEEPER", "WEATHER_SPEED", "PRIORITY_CLEANER"}:
            fast_benefit.append(name)
        if spe <= 85 or role in {"TR_SWEEPER", "BULKY_PIVOT"}:
            tr_benefit.append(name)
        elif 86 <= spe <= 115:
            tr_partial.append(name)
        if spe >= 130:
            tr_hurts.append(name)
        slots.append(slot)

    if "tailwind" in modes and "trick_room" in modes:
        if len(fast_benefit) >= 3:
            identity = "FAST_PRIMARY_WITH_BACKUP_TR"
            summary = "Tailwind/fast pressure is the main speed plan; Trick Room should be backup, reverse-TR, or a matchup-specific line."
            warnings.append({"code": "WARN_TRICK_ROOM_BACKUP_NOT_MAIN_MODE", "detail": "Most of the team is medium-fast/fast; do not call this a full Trick Room team without matchup-specific speed receipts."})
        elif len(tr_benefit) >= 3:
            identity = "TR_PRIMARY_WITH_FAST_OFFMODE"
            summary = "Trick Room can be the main mode, but fast slots need explicit off-mode usage."
        else:
            identity = "DUAL_MODE_NEEDS_EXPLANATION"
            summary = "Tailwind and Trick Room both exist, but they help different slots; explain which lead/mode is active."
        warnings.append({"code": "WARN_DUAL_SPEED_MODE_CONFLICT", "detail": "Tailwind and Trick Room pull speed order in opposite directions; public output must separate modes."})
        warnings.append({"code": "WARN_TRICK_ROOM_MAY_HELP_OPPONENT", "detail": "Do not recommend Trick Room into vague 'slow/bulky teams'; compare active Speed buckets first because TR may help the opponent."})
    elif "tailwind" in modes:
        identity = "TAILWIND_PRIMARY"
        summary = "Tailwind is the explicit speed-control plan."
    elif "trick_room" in modes:
        identity = "TRICK_ROOM_PRIMARY_OR_REVERSE"
        summary = "Trick Room is present; verify that the intended active attackers are slower than the opponent before recommending setup."
        if tr_hurts:
            warnings.append({"code": "WARN_FAST_MON_HURT_BY_TRICK_ROOM", "detail": f"Fast slots become worse under Trick Room: {', '.join(tr_hurts[:4])}."})
    else:
        identity = "NO_EXPLICIT_SPEED_CONTROL"
        summary = "No Tailwind/Trick Room speed-control mode detected."

    status = "pass_with_warnings" if warnings else "pass"
    return {
        "entity": "speed_plan_receipt",
        "status": status,
        "team_speed_identity": identity,
        "team_speed_modes": modes,
        "summary": summary,
        "slots": slots,
        "tailwind_beneficiaries": fast_benefit,
        "trick_room_beneficiaries": tr_benefit,
        "trick_room_partial_beneficiaries": tr_partial,
        "trick_room_hurts": tr_hurts,
        "warnings": warnings,
        "rule": "Do not recommend Tailwind or Trick Room from vague labels like fast/slow/bulky. Compare actual Speed receipts of intended active Pokémon first.",
    }


def verify_speedplan(team_payload) -> dict:
    receipt = team_payload if isinstance(team_payload, dict) and team_payload.get("mode") == "full_team_verification" else verify_team(team_payload)
    return evaluate_speed_plan(receipt)


def _lead_verdict_from_kind(kind: str, speed_plan: dict) -> str:
    if kind == "main_pressure":
        return "main lead"
    if kind == "anti_fast":
        return "anti-fast lead"
    if kind == "reverse_tr":
        return "backup / reverse-TR lead"
    return "candidate lead"


def evaluate_lead_plan(team_receipt: dict) -> dict:
    """v29.38: produce short T1-T2 lead candidates from verified set data.

    Lead plans are intentionally conservative: they surface candidate lines and
    risks. They do not replace matchup-specific speed/damage/board receipts.
    """
    speed_plan = team_receipt.get("team_gates", {}).get("speed_plan") or evaluate_speed_plan(team_receipt)
    sets = team_receipt.get("sets", [])
    candidates = []
    warnings = []

    # 1) Main pressure lead: attacker with Earthquake + Ground-immune partner, if present.
    for r in sets:
        move_ids = _slot_move_ids(r)
        if "earthquake" not in move_ids:
            continue
        eq_user = _slot_display_name_from_receipt(r)
        partner = None
        for p in sets:
            if p is r:
                continue
            pg = p.get("active_form", {}).get("active_form", p.get("pokemon_gate", {}))
            type_rec = verify_type_effectiveness("Ground", pg.get("types", ""))
            if type_rec.get("status") == "pass" and type_rec.get("total_type_multiplier") == 0.0:
                partner = p; break
        if partner:
            p_moves = _slot_move_display_map(partner)
            r_moves = _slot_move_display_map(r)
            turn1_partner = next((p_moves[m] for m in ["heatwave", "weatherball", "hurricane", "tailwind", "protect"] if m in p_moves), "verified attack / Protect")
            turn1_user = r_moves.get("earthquake", "verified attack")
            candidates.append({
                "lead": [_slot_display_name_from_receipt(partner), eq_user],
                "kind": "main_pressure",
                "plan": "safe spread/pressure line with Earthquake partner immunity",
                "turn_1": [turn1_partner, turn1_user],
                "turn_2": ["continue pressure or pivot after board check", "avoid Earthquake beside grounded allies"],
                "good_into": "mid-speed boards where immediate pressure is stronger than setting speed control",
                "risk": "Earthquake safety only applies beside this immune partner; re-check when switching.",
                "verdict": _lead_verdict_from_kind("main_pressure", speed_plan),
            })
            break

    # 2) Anti-fast: Tailwind setter + best fast/pressure partner.
    tw_setters = [r for r in sets if "tailwind" in _slot_move_ids(r)]
    if tw_setters:
        setter = max(tw_setters, key=_slot_speed_from_receipt)
        partner_pool = [r for r in sets if r is not setter]
        partner = max(partner_pool, key=_slot_speed_from_receipt) if partner_pool else None
        if partner:
            s_moves = _slot_move_display_map(setter)
            p_moves = _slot_move_display_map(partner)
            candidates.append({
                "lead": [_slot_display_name_from_receipt(setter), _slot_display_name_from_receipt(partner)],
                "kind": "anti_fast",
                "plan": "set Tailwind, then let the partner pressure under doubled Speed",
                "turn_1": [s_moves.get("tailwind", "Tailwind"), p_moves.get("protect") or next((v for k, v in p_moves.items() if k != "tailwind"), "verified attack / Protect")],
                "turn_2": ["attack under Tailwind", "use Protect/pivot if the setter is threatened"],
                "good_into": "teams that outspeed your key attackers before speed control",
                "risk": "Tailwind does not fix priority or bad defensive positioning.",
                "verdict": _lead_verdict_from_kind("anti_fast", speed_plan),
            })

    # 3) TR / reverse-TR: Trick Room setter + slow/priority partner.
    tr_setters = [r for r in sets if "trickroom" in _slot_move_ids(r)]
    if tr_setters:
        setter = min(tr_setters, key=_slot_speed_from_receipt)
        partner_pool = [r for r in sets if r is not setter]
        partner = min(partner_pool, key=_slot_speed_from_receipt) if partner_pool else None
        if partner:
            s_moves = _slot_move_display_map(setter)
            p_moves = _slot_move_display_map(partner)
            candidates.append({
                "lead": [_slot_display_name_from_receipt(setter), _slot_display_name_from_receipt(partner)],
                "kind": "reverse_tr",
                "plan": "use Trick Room only when the active slow mode benefits your side, or to reverse opponent Trick Room",
                "turn_1": [s_moves.get("trickroom", "Trick Room only if speedplan favors it"), p_moves.get("protect") or next(iter(p_moves.values()), "verified support / Protect")],
                "turn_2": ["slow-mode pressure if TR is up", "do not set TR into opponents slower than your active attackers"],
                "good_into": "mid-fast boards where your slow attackers move first after TR, or existing opposing TR that needs reversal",
                "risk": "Trick Room is priority -7 and may help slower opponents; needs speedplan/board check.",
                "verdict": _lead_verdict_from_kind("reverse_tr", speed_plan),
            })
            if speed_plan.get("team_speed_identity") in {"FAST_PRIMARY_WITH_BACKUP_TR", "DUAL_MODE_NEEDS_EXPLANATION"}:
                warnings.append({"code": "WARN_TRICK_ROOM_BACKUP_NOT_MAIN_MODE", "detail": "TR lead is a backup/reverse line unless speed receipts show the active attackers benefit."})

    # De-duplicate by lead tuple while preserving order and cap at 3.
    seen = set(); uniq = []
    for c in candidates:
        key = tuple(c.get("lead", []))
        if key in seen:
            continue
        seen.add(key); uniq.append(c)
    candidates = uniq[:3]
    if not candidates and len(sets) >= 2:
        warnings.append({"code": "WARN_LEAD_PLAN_HEURISTIC_EMPTY", "detail": "No obvious Tailwind/TR/Earthquake-safe candidate lead was detected; matchup-specific lead planning required."})
    return {
        "entity": "lead_plan_receipt",
        "status": "pass_with_warnings" if warnings else "pass",
        "candidate_leads": candidates,
        "warnings": warnings,
        "rule": "Lead planning must show Turn 1-2 candidate lines and rejected/conditional lines; do not jump from move presence to a final game plan.",
    }


def verify_leadplan(team_payload) -> dict:
    receipt = team_payload if isinstance(team_payload, dict) and team_payload.get("mode") == "full_team_verification" else verify_team(team_payload)
    return evaluate_lead_plan(receipt)



# v29.39 semanticthreataudit / statclaim / itemthreatprofile gates
RESIST_BERRY_TYPE_BY_ID = {}
STAT_ADJECTIVE_PATTERN = re.compile(r"(?i)(ถึกสองด้าน|ถึกทั้งสองด้าน|ถึก|บาง|เร็ว|ช้า|bulky|frail|fast|slow|mixed\s+bulk|physical\s+wall|special\s+wall|two[-\s]?sided\s+bulk)")
TWO_SIDED_BULK_PATTERN = re.compile(r"(?i)(ถึกสองด้าน|ถึกทั้งสองด้าน|mixed\s+bulk|two[-\s]?sided\s+bulk|bulky\s+on\s+both\s+sides)")
STAT_RECEIPT_WORD_PATTERN = re.compile(r"(?i)(HP|Atk|Attack|Def|Defense|SpA|Sp\.\s*Atk|Special\s+Attack|SpD|Sp\.\s*Def|Special\s+Defense|Spe|Speed|base\s+stat|displayed\s+stat|stat\s+receipt)\s*[:=]?\s*\d{1,3}|\d{1,3}\s*/\s*\d{1,3}\s*/\s*\d{1,3}")
MECHANIC_STAGE_CLAIM_PATTERN = re.compile(r"(?i)(\+\s*[1-6]|stage|ขั้น|ระดับ).{0,35}(Atk|Attack|Def|Defense|SpA|Sp\.\s*Atk|Special\s+Attack|SpD|Sp\.\s*Def|Special\s+Defense|Speed|Spe|stat)|(?:Atk|Attack|Def|Defense|SpA|Sp\.\s*Atk|Special\s+Attack|SpD|Sp\.\s*Def|Speed|Spe).{0,35}(\+\s*[1-6]|stage|ขั้น|ระดับ)")
MOVE_SEQUENCE_CLAIM_PATTERN = re.compile(r"(?i)(first\s+turn|next\s+turn|2[-\s]?turn|two[-\s]?turn|immediately\s+in\s+rain|เทิร์นแรก|เทิร์นถัด|สองเทิร์น|ชาร์จ|ยิงทันที|ฝน.*ทันที)")
DESCRIPTION_08_CAVEAT_PATTERN = re.compile(r"(?i)(08\s+description|description\s+จาก\s+08|คำอธิบาย\s+08|source\s+08)")


def _berry_type_from_item_receipt(item_receipt: dict) -> str:
    """Return the attacking type a resist Berry reduces, using local 08 description."""
    if not item_receipt or item_receipt.get("status") != "pass":
        return ""
    item_id = normalize_id(item_receipt.get("id", item_receipt.get("name", "")))
    if item_id in RESIST_BERRY_TYPE_BY_ID:
        return RESIST_BERRY_TYPE_BY_ID[item_id]
    desc = str(item_receipt.get("description", ""))
    m = re.search(r"supereffective\s+([A-Za-z]+)-type\s+attack", desc, re.I)
    if m:
        t = normalize_id(m.group(1))
        if t in VALID_TYPES:
            RESIST_BERRY_TYPE_BY_ID[item_id] = t
            return t
    return ""


def _defender_query_from_set_receipt(r: dict) -> str:
    af = r.get("active_form", {}) or {}
    active = af.get("active_form", {}) or {}
    return active.get("types") or r.get("pokemon_gate", {}).get("types", "") or r.get("input", {}).get("pokemon", "")


def _base_stats_from_set_receipt(r: dict) -> dict:
    af = r.get("active_form", {}) or {}
    active = af.get("active_form", {}) or {}
    stats = active.get("stats") or r.get("pokemon_gate", {}).get("stats") or {}
    out = {}
    for k in STAT_KEYS:
        try:
            out[k] = int(stats.get(k, 0) or 0)
        except Exception:
            out[k] = 0
    return out


def _bulk_profile_from_base_stats(stats: dict) -> dict:
    hp = int(stats.get("hp", 0) or 0); dfv = int(stats.get("def", 0) or 0); spd = int(stats.get("spd", 0) or 0); spe = int(stats.get("spe", 0) or 0)
    physical_bulk = "high" if hp >= 95 and dfv >= 100 or dfv >= 120 else ("low" if hp <= 75 or dfv <= 70 else "medium")
    special_bulk = "high" if hp >= 95 and spd >= 100 or spd >= 120 else ("low" if hp <= 75 or spd <= 70 else "medium")
    speed_bucket = "fast" if spe >= 110 else ("slow" if spe <= 60 else "mid")
    mixed_bulk_ok = physical_bulk == "high" and special_bulk == "high"
    return {
        "physical_bulk": physical_bulk,
        "special_bulk": special_bulk,
        "speed_bucket": speed_bucket,
        "mixed_bulk_ok": mixed_bulk_ok,
        "summary": f"HP {hp} / Def {dfv} / SpD {spd} / Spe {spe}: physical_bulk={physical_bulk}, special_bulk={special_bulk}, speed={speed_bucket}",
    }


def evaluate_threat_audit(team_receipt: dict) -> dict:
    """Build a semantic defensive profile before item/risk prose.

    This gate turns local typechart + base stat + team board facts into a compact
    profile. It is not a damage calculator; KO/survival still need damage/sequence receipts.
    """
    out = {
        "entity": "threat_audit_receipt",
        "status": "pass",
        "slots": [],
        "failures": [],
        "warnings": [],
        "rule": "Risk/item/stat explanations require a semantic threat audit. Lint pass is not semantic verification.",
    }
    sets = team_receipt.get("sets", []) or []
    # Current local board-risk support: ally Earthquake. Keep conservative and data-driven.
    ally_spread_sources = []
    for src in sets:
        for m in src.get("moves", []) or []:
            mid = normalize_id(m.get("move_id", m.get("move_query", "")))
            if mid == "earthquake":
                ally_spread_sources.append({
                    "slot": src.get("slot"),
                    "pokemon": _slot_display_name_from_receipt(src),
                    "move": m.get("move_name", "Earthquake"),
                    "type": normalize_id(m.get("type", "Ground")) or "ground",
                    "display": m.get("display", "🟤 Earthquake"),
                })
    for r in sets:
        name = _slot_display_name_from_receipt(r)
        defender_query = _defender_query_from_set_receipt(r)
        type_receipts = []
        weaknesses = []
        resistances = []
        immunities = []
        for atk in sorted(VALID_TYPES):
            rec = verify_type_effectiveness(atk, defender_query)
            if rec.get("status") != "pass":
                continue
            mult = float(rec.get("total_type_multiplier", 1.0))
            slim = {k: rec.get(k) for k in ["entity", "attacking_type", "defender_types", "total_type_multiplier", "label", "display", "status"]}
            type_receipts.append(slim)
            row = {"type": rec.get("attacking_type"), "type_id": atk, "multiplier": mult, "display": rec.get("display")}
            if mult == 0.0:
                immunities.append(row)
            elif mult < 1.0:
                resistances.append(row)
            elif mult > 1.0:
                weaknesses.append(row)
        base_stats = _base_stats_from_set_receipt(r)
        bulk_profile = _bulk_profile_from_base_stats(base_stats)
        board_risks = []
        for src in ally_spread_sources:
            if src.get("slot") == r.get("slot"):
                continue
            rec = verify_type_effectiveness(src.get("type", "ground"), defender_query)
            if rec.get("status") != "pass":
                continue
            mult = float(rec.get("total_type_multiplier", 1.0))
            if mult > 0:
                severity = "high" if mult >= 2.0 else ("medium" if mult == 1.0 else "low")
                board_risks.append({
                    "source_slot": src.get("slot"),
                    "source": f"ally {src.get('pokemon')} {src.get('move')}",
                    "move": src.get("move"),
                    "type": _TYPE_NAME.get(src.get("type"), src.get("type", "")),
                    "type_id": src.get("type"),
                    "multiplier": mult,
                    "severity": severity,
                    "typechart_receipt": rec.get("display"),
                })
        item = r.get("item", {}) or {}
        berry_type = _berry_type_from_item_receipt(item)
        slot = {
            "slot": r.get("slot"),
            "pokemon": name,
            "types": _type_display(defender_query),
            "weaknesses": weaknesses,
            "resistances": resistances,
            "immunities": immunities,
            "base_stats": base_stats,
            "stat_profile": bulk_profile,
            "board_risks": board_risks,
            "defensive_item": item.get("name", r.get("input", {}).get("item", "")),
            "resist_berry_type": _TYPE_NAME.get(berry_type, "") if berry_type else "",
            "typechart_receipt_count": len(type_receipts),
            "sample_typechart_receipts": [x.get("display") for x in type_receipts[:6]],
            "status": "pass",
            "warnings": [],
        }
        if TWO_SIDED_BULK_PATTERN.search(_reason_text_from_set(r.get("input", {}) or "")) and not bulk_profile.get("mixed_bulk_ok"):
            warn = {"code": "WARN_BULK_REASON_CONFLICTS_BASE_STATS", "pokemon": name, "detail": bulk_profile.get("summary")}
            slot["warnings"].append(warn); out["warnings"].append(warn)
        out["slots"].append(slot)
    if out["failures"]:
        out["status"] = "fail"
    elif out["warnings"]:
        out["status"] = "pass_with_warnings"
    return out


def verify_threataudit(team_payload) -> dict:
    receipt = team_payload if isinstance(team_payload, dict) and team_payload.get("mode") == "full_team_verification" else verify_team(team_payload)
    return evaluate_threat_audit(receipt)


def evaluate_item_threat_fit(team_receipt: dict) -> dict:
    """Check defensive item reasoning against the semantic threat profile and board risk."""
    threat = team_receipt.get("team_gates", {}).get("threat_audit") or evaluate_threat_audit(team_receipt)
    threat_slots = {s.get("slot"): s for s in threat.get("slots", []) or []}
    out = {
        "entity": "item_threat_fit_receipt",
        "status": "pass",
        "slots": [],
        "failures": [],
        "warnings": [],
        "rule": "Defensive items must answer the actual weakness profile and board risk, not a single remembered weakness.",
    }
    for r in team_receipt.get("sets", []) or []:
        inp = r.get("input", {}) or {}
        name = _slot_display_name_from_receipt(r)
        item = r.get("item", {}) or {}
        item_name = item.get("name", inp.get("item", ""))
        berry_type = _berry_type_from_item_receipt(item)
        prof = threat_slots.get(r.get("slot"), {})
        weaknesses = prof.get("weaknesses", []) or []
        board_risks = prof.get("board_risks", []) or []
        reason_text = _reason_text_from_set(inp)
        slot = {
            "slot": r.get("slot"),
            "pokemon": name,
            "item": item_name,
            "resist_berry_type": _TYPE_NAME.get(berry_type, "") if berry_type else "",
            "weakness_count": len(weaknesses),
            "weaknesses": weaknesses,
            "board_risks": board_risks,
            "status": "pass",
            "warnings": [],
        }
        if not berry_type:
            out["slots"].append(slot)
            continue
        selected_weak = next((w for w in weaknesses if normalize_id(w.get("type_id") or w.get("type")) == berry_type), None)
        if not selected_weak:
            fail = {"code": "FAIL_ITEM_THREAT_PROFILE_MISSING", "pokemon": name, "item": item_name, "detail": f"{item_name} reduces {_TYPE_NAME.get(berry_type, berry_type)} but threat audit does not show that type as a super-effective weakness."}
            slot["status"] = "fail"; out["failures"].append(fail)
        if len(weaknesses) > 1:
            warn = {"code": "WARN_RESIST_BERRY_SELECTED_FROM_SINGLE_WEAKNESS", "pokemon": name, "item": item_name, "detail": "This holder has multiple weaknesses; item reasoning must compare all weakness candidates, not only the selected berry type."}
            slot["warnings"].append(warn); out["warnings"].append(warn)
        higher_board = [b for b in board_risks if normalize_id(b.get("type_id") or b.get("type")) != berry_type and float(b.get("multiplier", 1.0) or 1.0) >= 2.0 and b.get("severity") == "high"]
        if higher_board:
            warn = {"code": "WARN_ITEM_MISALIGNED_WITH_BOARD_THREAT", "pokemon": name, "item": item_name, "detail": "A different high-severity board risk exists: " + "; ".join(f"{b.get('source')} {b.get('typechart_receipt')}" for b in higher_board[:3])}
            slot["warnings"].append(warn); out["warnings"].append(warn)
            sel_name = _TYPE_NAME.get(berry_type, berry_type)
            # If the item reason talks up the selected berry/type but ignores the higher board-risk type, fail.
            if reason_text and re.search(re.escape(sel_name) + r"|" + re.escape(item_name), reason_text, re.I):
                missing_types = [str(b.get("type", "")) for b in higher_board if str(b.get("type", "")) and not re.search(str(b.get("type", "")), reason_text, re.I)]
                if missing_types:
                    fail = {"code": "FAIL_ITEM_REASON_IGNORES_HIGHER_BOARD_RISK", "pokemon": name, "item": item_name, "detail": f"Item reason mentions {item_name}/{sel_name} but ignores higher board risk type(s): {', '.join(sorted(set(missing_types)))}."}
                    slot["status"] = "fail"; out["failures"].append(fail)
        out["slots"].append(slot)
    if out["failures"]:
        out["status"] = "fail"
    elif out["warnings"]:
        out["status"] = "pass_with_warnings"
    return out


def verify_itemthreatfit(team_payload) -> dict:
    receipt = team_payload if isinstance(team_payload, dict) and team_payload.get("mode") == "full_team_verification" else verify_team(team_payload)
    return evaluate_item_threat_fit(receipt)

def _extract_team_list(team_payload):
    """Accept either a raw list of set objects or {"team": [...], "item_clause": true, "spread_required": true}."""
    if isinstance(team_payload, list):
        return team_payload, True, True
    if isinstance(team_payload, dict):
        team = team_payload.get("team", team_payload.get("sets", []))
        item_clause = bool(team_payload.get("item_clause", True))
        spread_required = bool(team_payload.get("spread_required", True))
        return team, item_clause, spread_required
    return [], True, True



TYPE_EMOJI_MAP = {
    "normal": "⚪", "fire": "🔥", "water": "💧", "electric": "⚡",
    "grass": "🌿", "ice": "🧊", "fighting": "🤜", "poison": "☠️",
    "ground": "🟤", "flying": "🪽", "psychic": "🔮", "bug": "🐞",
    "rock": "🪨", "ghost": "👻", "dragon": "🐉", "dark": "🌑",
    "steel": "⚙️", "fairy": "🧚",
}

def _type_display(types_text: str) -> str:
    """Return public type display with both emoji and name.

    v29.38 rule: type emoji are not optional. Cards, compact tables, and
    detailed sets should show e.g. `🌿 Grass / 👻 Ghost`, not bare
    `Grass/Ghost`.
    """
    types = _parse_types_field(types_text)
    if not types:
        return str(types_text or "")
    parts = []
    for t in types:
        name = _TYPE_NAME.get(t, t.title())
        emoji = TYPE_EMOJI_MAP.get(t, "")
        parts.append((emoji + " " + name).strip())
    return " / ".join(parts)


def _receipt_source_label(key: str) -> str:
    return {
        "pokemon": "01",
        "abilities": "01",
        "items": "08",
        "moves": "05-07",
        "stat_spreads": "verify.py team/spread",
        "displayed_stats": "verify.py stat",
        "active_form": "verify.py active-form",
        "battle_stats": "verify.py stat via active-form resolver",
        "unique_items": "verify.py team",
        "compatibility": "00/04 + verify.py team",
        "priority": "verify.py priority/mechanic",
        "public_render": "verify.py render",
        "move_emoji": "move.display from 05-07 receipt",
        "team_fit": "verify.py teamfit",
        "threat_audit": "verify.py threataudit",
        "item_threat_fit": "verify.py itemthreatfit",
        "provenance": "verify.py teamfit",
    }.get(key, "verify.py")


def build_public_render(team_receipt: dict) -> dict:
    """Build a copy-safe public-render payload from verifier receipts.

    The assistant should copy from this payload rather than reconstructing move
    emoji, stat displays, or gate summaries by hand.
    """
    sets = team_receipt.get("sets", [])
    total_sets = len(sets)
    pokemon_pass = sum(1 for r in sets if r.get("pokemon_gate", {}).get("status") == "pass")
    ability_pass = sum(1 for r in sets if r.get("ability", {}).get("status") == "pass")
    item_pass = sum(1 for r in sets if r.get("item", {}).get("status") == "pass")
    active_pass = sum(1 for r in sets if r.get("active_form", {}).get("status") == "pass")
    active_gate = team_receipt.get("team_gates", {}).get("active_form_resolution", {})
    move_receipts = [m for r in sets for m in r.get("moves", [])]
    move_pass = sum(1 for m in move_receipts if m.get("status") == "pass")
    move_display_pass = sum(1 for m in move_receipts if m.get("status") == "pass" and m.get("emoji") and m.get("display") == f"{m.get('emoji')} {m.get('move_name')}")
    spread_gate = team_receipt.get("team_gates", {}).get("stat_spreads_0_32_66", {})
    stat_gate = team_receipt.get("team_gates", {}).get("displayed_stats", {})
    unique_gate = team_receipt.get("team_gates", {}).get("unique_items_item_clause", {})
    compat_gate = team_receipt.get("team_gates", {}).get("team_compatibility", {})
    priority_gate = team_receipt.get("team_gates", {}).get("priority_mechanics", {})
    interaction_gate = team_receipt.get("team_gates", {}).get("mechanic_interactions", {})
    threatfit_gate = team_receipt.get("team_gates", {}).get("meta_threat_fit", {})
    teamfit_gate = team_receipt.get("team_gates", {}).get("team_fit", {})
    item_prov_gate = team_receipt.get("team_gates", {}).get("item_provenance", {})
    spread_prov_gate = team_receipt.get("team_gates", {}).get("spread_provenance", {})
    spreadfit_gate = team_receipt.get("team_gates", {}).get("spread_fit", {})
    speedplan_gate = team_receipt.get("team_gates", {}).get("speed_plan", {})
    leadplan_gate = team_receipt.get("team_gates", {}).get("lead_plan", {})
    threataudit_gate = team_receipt.get("team_gates", {}).get("threat_audit", {})
    itemthreatfit_gate = team_receipt.get("team_gates", {}).get("item_threat_fit", {})
    ascii_status = ascii_assets_status()

    render_ok = bool(team_receipt.get("team_ok")) and move_display_pass == move_pass and move_pass == total_sets * 4
    receipt_rows = [
        {"gate": "Pokémon", "result": f"{pokemon_pass}/{total_sets} PASS" if pokemon_pass == total_sets else f"{pokemon_pass}/{total_sets} FAIL", "source": _receipt_source_label("pokemon")},
        {"gate": "Abilities", "result": f"{ability_pass}/{total_sets} PASS" if ability_pass == total_sets else f"{ability_pass}/{total_sets} FAIL", "source": _receipt_source_label("abilities")},
        {"gate": "Items exist", "result": f"{item_pass}/{total_sets} PASS" if item_pass == total_sets else f"{item_pass}/{total_sets} FAIL", "source": _receipt_source_label("items")},
        {"gate": "Active form resolution", "result": str(active_gate.get("status", "pass" if active_pass == total_sets else "fail")).upper(), "source": _receipt_source_label("active_form")},
        {"gate": "Battle stat source", "result": str(stat_gate.get("status", "missing")).upper(), "source": _receipt_source_label("battle_stats")},
        {"gate": "Moves", "result": f"{move_pass}/{total_sets*4} PASS" if move_pass == total_sets*4 else f"{move_pass}/{total_sets*4} FAIL", "source": _receipt_source_label("moves")},
        {"gate": "Move emoji rendering", "result": f"{move_display_pass}/{move_pass} PASS" if move_display_pass == move_pass else f"{move_display_pass}/{move_pass} FAIL", "source": _receipt_source_label("move_emoji")},
        {"gate": "Stat spreads 0-32/66", "result": str(spread_gate.get("status", "missing")).upper(), "source": _receipt_source_label("stat_spreads")},
        {"gate": "Displayed stats", "result": str(stat_gate.get("status", "missing")).upper(), "source": _receipt_source_label("displayed_stats")},
        {"gate": "Unique items / Item Clause", "result": str(unique_gate.get("status", "missing")).upper(), "source": _receipt_source_label("unique_items")},
        {"gate": "Item provenance", "result": str(item_prov_gate.get("status", "missing")).upper(), "source": _receipt_source_label("provenance")},
        {"gate": "Spread provenance", "result": str(spread_prov_gate.get("status", "missing")).upper(), "source": _receipt_source_label("provenance")},
        {"gate": "Meta spread fit", "result": str(spreadfit_gate.get("status", "missing")).upper(), "source": "verify.py spreadfit"},
        {"gate": "Item / spread coherence", "result": str((team_receipt.get("team_gates", {}).get("item_spread_coherence", {}) or {}).get("status", "missing")).upper(), "source": _receipt_source_label("item_spread_coherence")},
        {"gate": "Team fit", "result": str(teamfit_gate.get("status", "missing")).upper(), "source": _receipt_source_label("team_fit")},
        {"gate": "Speed plan", "result": str(speedplan_gate.get("status", "missing")).upper(), "source": "verify.py speedplan"},
        {"gate": "Lead plan", "result": str(leadplan_gate.get("status", "missing")).upper(), "source": "verify.py leadplan"},
        {"gate": "Semantic threat audit", "result": str(threataudit_gate.get("status", "missing")).upper(), "source": "verify.py threataudit"},
        {"gate": "Item threat fit", "result": str(itemthreatfit_gate.get("status", "missing")).upper(), "source": "verify.py itemthreatfit"},
        {"gate": "Priority mechanics", "result": str(priority_gate.get("status", "pass")).upper(), "source": _receipt_source_label("priority")},
        {"gate": "Mechanic interactions", "result": str(interaction_gate.get("status", "pass")).upper(), "source": "verify.py interaction"},
        {"gate": "Meta threat fit", "result": str(threatfit_gate.get("status", "pass")).upper(), "source": "verify.py threatfit"},
        {"gate": "Team compatibility", "result": str(compat_gate.get("status", "missing")).upper(), "source": _receipt_source_label("compatibility")},
        {"gate": "Pokémon ASCII cards", "result": ("PASS" if ascii_status.get("status") == "pass" else "N/A"), "source": ascii_status.get("bundle_path", "assets/champions_ascii/ascii_bundle.json")},
        {"gate": "Public render", "result": "PASS" if render_ok else "FAIL", "source": _receipt_source_label("public_render")},
    ]

    team_table_rows = []
    set_note_blocks = []
    ally_safety_matrices = []
    teamfit_modes = teamfit_gate.get("team_speed_modes", []) if isinstance(teamfit_gate, dict) else []
    for r in sets:
        pg = r.get("pokemon_gate", {})
        af = r.get("active_form", {})
        active_pg = af.get("active_form", pg) if af.get("status") == "pass" else pg
        inp = r.get("input", {})
        tf_slots = {x.get("slot"): x for x in (team_receipt.get("team_gates", {}).get("team_fit", {}).get("slots", []) or [])}
        tf = tf_slots.get(r.get("slot"), {})
        moves = r.get("moves", [])
        move_displays = [m.get("display") or (f"{m.get('emoji','')} {m.get('move_name', m.get('move_query',''))}".strip()) for m in moves if m.get("status") == "pass"]
        stats = r.get("displayed_stats", {}).get("displayed_stats", {})
        stats_display = r.get("displayed_stats", {}).get("displayed_stats_display", _stat_display_fields(stats))
        spread_obj = r.get("spread", {})
        spread_display = spread_obj.get("display_verbose", spread_obj.get("display", ""))
        spread_compact = spread_obj.get("display_compact", spread_display)
        spread_total = spread_obj.get("display_total", f"{spread_obj.get('total','?')}/66")
        row = {
            "slot": r.get("slot"),
            "pokemon": af.get("display_name", active_pg.get("name", inp.get("pokemon", ""))),
            "pokemon_id": active_pg.get("id", pg.get("id", "")),
            "team_form_id": pg.get("id", ""),
            "active_form_id": active_pg.get("id", ""),
            "stat_source": af.get("stat_source", active_pg.get("id", "")),
            "type": _type_display(active_pg.get("types", pg.get("types", ""))),
            "role": inp.get("role", ""),
            "ability": r.get("ability", {}).get("ability_name", inp.get("ability", "")),
            "item": r.get("item", {}).get("name", inp.get("item", "")),
            "item_source": tf.get("item_source", _get_provenance(inp, "item")),
            "spread_source": tf.get("spread_source", _get_provenance(inp, "spread")),
            "speed_role": tf.get("speed_role", _set_speed_role(inp, r, team_receipt.get("team_gates", {}).get("team_fit", {}).get("team_speed_modes", []))),
            "verified_moves": " / ".join(move_displays),
            "nature": inp.get("nature", ""),
            "spread_display": spread_display,
            "spread_compact": spread_compact,
            "spread_total": spread_total,
            "displayed_stats": stats,
            "displayed_stats_display": stats_display,
            "pokemon_ascii_asset": active_pg.get("ascii_asset", _ascii_asset("pokemon", active_pg.get("id", pg.get("id", "")), active_pg.get("name", pg.get("name", "")))),
            "item_ascii_asset": {"status": "disabled", "reason": "v29.38 keeps item ASCII disabled; cards use Pokémon ASCII only"},
        }
        team_table_rows.append(row)
        set_note_blocks.append({
            "slot": row["slot"],
            "pokemon": row["pokemon"],
            "item": row["item"],
            "ability": row["ability"],
            "role": row["role"],
            "nature": row["nature"],
            "spread_display": row["spread_display"],
            "spread_compact": row.get("spread_compact", row["spread_display"]),
            "spread_total": row.get("spread_total", ""),
            "displayed_stats": row["displayed_stats"],
            "displayed_stats_display": row.get("displayed_stats_display", _stat_display_fields(row["displayed_stats"])),
            "stat_source": row.get("stat_source", ""),
            "moves_display": row["verified_moves"],
            "move_list": _move_display_list(moves),
            "item_source": row.get("item_source", ""),
            "spread_source": row.get("spread_source", ""),
            "speed_role": row.get("speed_role", ""),
            "spread_reason": _spread_reason_for_slot(inp, r, tf, teamfit_modes),
            "spread_fit": next((x for x in (team_receipt.get("team_gates", {}).get("spread_fit", {}).get("slots", []) or []) if x.get("slot") == r.get("slot")), {}),
            "pokemon_ascii_asset": row.get("pokemon_ascii_asset", {}),
            "item_ascii_asset": row.get("item_ascii_asset", {}),
        })


    # Spread-move ally safety matrices for common ally-hitting moves.
    # Currently implements Earthquake/Ground; conservative enough to stop broad "EQ sweep" claims.
    for r in sets:
        moves = r.get("moves", [])
        move_ids = {normalize_id(m.get("move_id", m.get("move_query", ""))) for m in moves}
        if "earthquake" not in move_ids:
            continue
        user_name = r.get("active_form", {}).get("display_name", r.get("pokemon_gate", {}).get("name", r.get("input", {}).get("pokemon", "unknown")))
        rows = []
        for p in sets:
            if p is r:
                continue
            partner = p.get("active_form", {}).get("active_form", p.get("pokemon_gate", {}))
            partner_name = p.get("active_form", {}).get("display_name", partner.get("name", p.get("input", {}).get("pokemon", "unknown")))
            types_text = partner.get("types", "")
            receipt = verify_type_effectiveness("Ground", types_text)
            mult = receipt.get("total_type_multiplier") if receipt.get("status") == "pass" else None
            partner_moves = {normalize_id(m.get("move_id", m.get("move_query", ""))) for m in p.get("moves", [])}
            has_protect = "protect" in partner_moves
            if mult == 0.0:
                safe = "✅ Safe"
                reason = "Ground immunity from typing"
            elif has_protect:
                safe = "⚠️ Needs Protect"
                reason = "Takes Ground damage unless Protect/positioning is used"
            else:
                safe = "❌ Unsafe"
                reason = "Takes Ground damage; avoid this pairing during Earthquake"
            rows.append({
                "partner": partner_name,
                "partner_types": _type_display(types_text),
                "safe": safe,
                "reason": reason,
                "type_multiplier": mult,
                "typechart_receipt": receipt,
            })
        ally_safety_matrices.append({
            "move": "Earthquake",
            "user": user_name,
            "rows": rows,
            "rule": "Spread moves that can hit allies need slot-by-slot safety, not a generic warning.",
        })

    return {
        "status": "pass" if render_ok else "fail",
        "rule": "Public output must copy move.display/stat/damage/type/priority fields from verifier receipts; do not reconstruct them manually.",
        "receipt_rows": receipt_rows,
        "team_table_rows": team_table_rows,
        "set_note_blocks": set_note_blocks,
        "warnings": team_receipt.get("warnings", []),
        "ally_safety_matrices": ally_safety_matrices,
        "mechanic_interactions": team_receipt.get("team_gates", {}).get("mechanic_interactions", {}).get("receipts", []),
        "meta_threat_fit": team_receipt.get("team_gates", {}).get("meta_threat_fit", {}),
        "spread_fit": team_receipt.get("team_gates", {}).get("spread_fit", {}),
        "speed_plan": team_receipt.get("team_gates", {}).get("speed_plan", {}),
        "lead_plan": team_receipt.get("team_gates", {}).get("lead_plan", {}),
        "fail_codes": [] if render_ok else ["FAIL_PUBLIC_RENDER_GATE"],
    }



def _trim_ascii_for_card(text: str, max_lines: int = 18, max_width: int = 64) -> str:
    """Return a bounded Pokémon ASCII block suitable for inline chat cards."""
    if not text:
        return ""
    lines = str(text).splitlines()
    # Drop fully empty padding at top/bottom while preserving internal spacing.
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    lines = lines[:max_lines]
    return "\n".join(line[:max_width].rstrip() for line in lines)


def _moves_as_chips(move_list) -> str:
    return " ".join(f"`{m}`" for m in (move_list or []))

def _html_chip(text: str) -> str:
    return (
        '<span style="display:inline-block; background:#111; border-radius:8px; '
        'padding:4px 10px; margin:2px 4px 2px 0; font-size:13px; color:#f3f3f3;">'
        + html.escape(str(text)) +
        '</span>'
    )

def _render_team_html_cards_from_render(render: dict) -> str:
    """Canonical Claude HTML card payload.

    This is the only allowed Claude card layout for v29.37+:
    vertical stack of rounded HTML cards, Pokémon ASCII on the left,
    verified set data and move chips on the right. It intentionally does not
    draw ASCII/text boxes and does not render item ASCII.

    Important: in Claude, this HTML is a widget/artifact payload. Do not paste
    the raw HTML as normal chat text. If no HTML/widget renderer is available,
    use the inline Markdown ASCII card fallback instead.
    """
    cards = []
    table_rows = render.get("team_table_rows", []) or []
    for block in render.get("set_note_blocks", []) or []:
        trow = next((r for r in table_rows if r.get("slot") == block.get("slot")), {})
        pokemon_ascii = _trim_ascii_for_card((block.get("pokemon_ascii_asset") or {}).get("text", ""), max_lines=16, max_width=58)
        title = html.escape(str(block.get("pokemon", "")))
        item = html.escape(str(block.get("item", ""))) if block.get("item") else ""
        type_text = html.escape(str(trow.get("type", "")))
        ability = html.escape(str(block.get("ability", "")))
        nature = html.escape(str(block.get("nature", "")))
        spread = html.escape(str(block.get("spread_display", "")))
        total = html.escape(str(block.get("spread_total", "")))
        stats_disp = (block.get("displayed_stats_display", {}) or {}).get("compact", "")
        stats = html.escape(str(stats_disp))
        move_html = "".join(_html_chip(m) for m in block.get("move_list", []) or [])
        meta_line = " · ".join([x for x in [type_text, item, ability] if x])
        spread_line = " · ".join([x for x in [nature, spread] if x])
        if total:
            spread_line = (spread_line + " · " if spread_line else "") + "Total " + total
        card = (
            '<div style="background:var(--surface-2); border:0.5px solid var(--border); border-radius:12px; '
            'padding:1rem 1.25rem; display:flex; gap:16px; align-items:flex-start; max-width:760px; margin:12px 0;">\n'
            '  <pre style="margin:0; font-family:var(--font-mono); font-size:11px; line-height:1.15; color:var(--text-secondary); white-space:pre; flex-shrink:0; overflow:hidden;">'
            + html.escape(pokemon_ascii) +
            '</pre>\n'
            '  <div style="flex:1; min-width:0;">\n'
            '    <p style="font-weight:500; font-size:15px; margin:0 0 2px;">' + title + '</p>\n'
            '    <p style="font-size:13px; color:var(--text-secondary); margin:0 0 10px;">' + meta_line + '</p>\n'
            '    <div style="font-size:13px; color:var(--text-secondary); margin-bottom:8px;">' + spread_line + '</div>\n'
            '    <div style="font-size:13px; margin-bottom:10px;">' + stats + '</div>\n'
            '    <div style="display:flex; flex-wrap:wrap; gap:6px;">' + move_html + '</div>\n'
            '  </div>\n'
            '</div>'
        )
        cards.append(card)
    return '<div style="display:flex; flex-direction:column; gap:12px;">\n' + "\n".join(cards) + "\n</div>\n"

def render_team_markdown(team_payload, style: str = "compact", platform: str = "portable") -> str:
    """Return a public-safe markdown draft generated from verifier receipts.

    v29.38 platform-aware card rendering + decision trace:
    - default output is compact/no-card text.
    - after normal full-team output, ask whether the user wants a platform-appropriate card view.
    - Claude-only card requests use the canonical --platform claude --style claude-html-card template.
      That HTML must be displayed through the platform HTML/widget/artifact renderer, not pasted raw.
    - non-Claude/uncertain platforms use inline Markdown ASCII card only.
    - style=card is platform-aware: Claude -> canonical HTML payload, non-Claude -> inline ASCII.
    - no ASCII box card layout; preserve verifier emoji everywhere.
    - all names, moves, stats, type, and mechanics still come from receipts.
    """
    receipt = verify_team(team_payload)
    render = receipt.get("public_render") or build_public_render(receipt)
    ascii_ok = ascii_assets_status().get("status") == "pass"
    style = (style or "compact").strip().lower()
    platform = (platform or "portable").strip().lower()
    is_claude_platform = platform in {"claude", "anthropic", "claude-skill"}
    if style in {"platform-card", "team-card", "card-auto", "card", "cards"}:
        style = "claude-html-card" if is_claude_platform else "inline-ascii-card"
    html_card = style in {"claude-html-card", "html-card", "claude-card"}
    if html_card:
        if not is_claude_platform:
            # Never suggest or emit Claude HTML card on non-Claude/unknown platforms.
            style = "inline-ascii-card"
        else:
            if not receipt.get("team_ok"):
                return render_team_markdown(team_payload, style="compact", platform=platform)
            return _render_team_html_cards_from_render(render)
    compact = style in {"compact", "no-ascii", "text", "table", "standard", "default", "no-card"}
    markdown_card = style in {"markdown-ascii-card", "ascii-card", "portable-card", "inline-ascii-card", "inline-ascii", "inline-card"}
    lines = []
    if not receipt.get("team_ok"):
        lines.append("## 🔒 Audit / fix required")
        lines.append("")
        lines.append("ทีมยังไม่ผ่าน verifier จึงยังไม่ใช่ final team")
        lines.append("")
    lines.append("## 🔒 Verification receipt")
    lines.append("| Gate | Result | Source |")
    lines.append("|---|---:|---|")
    for row in render.get("receipt_rows", []):
        lines.append(f"| {row['gate']} | {row['result']} | {row['source']} |")
    lines.append("")
    if receipt.get("team_ok"):
        lines.append("## ✅ Team at a glance")
        lines.append("| Slot | Pokémon | Type | Item | Ability | Role | Moves |")
        lines.append("|---:|---|---|---|---|---|---|")
        for row in render.get("team_table_rows", []):
            lines.append(f"| {row['slot']} | {row['pokemon']} | {row['type']} | {row['item']} | {row['ability']} | {row['role']} | {row['verified_moves']} |")
        lines.append("")
        sp = render.get("speed_plan", {}) or {}
        lp = render.get("lead_plan", {}) or {}
        if sp:
            lines.append("## 🧠 Decision trace")
            lines.append(f"**Team identity:** `{sp.get('team_speed_identity','')}` — {sp.get('summary','')}")
            lines.append("")
            lines.append("### ⚡ Speed-mode check")
            lines.append("| Mode | Who benefits | Who is hurt / condition |")
            lines.append("|---|---|---|")
            lines.append(f"| Tailwind | {', '.join(sp.get('tailwind_beneficiaries', []) or ['—'])} | ใช้เมื่อ key attackers ต้องชนะ speed race |")
            tr_bits = list(sp.get('trick_room_beneficiaries', []) or [])
            if sp.get('trick_room_partial_beneficiaries'):
                tr_bits += [f"partial: {x}" for x in sp.get('trick_room_partial_beneficiaries', [])]
            lines.append(f"| Trick Room | {', '.join(tr_bits or ['—'])} | Hurts: {', '.join(sp.get('trick_room_hurts', []) or ['—'])}; ห้ามใช้แค่เพราะคู่ต่อสู้ดูช้า/ถึก |")
            if sp.get("warnings"):
                rejected = []
                for w in sp.get("warnings", []):
                    code = w.get("code", "WARN")
                    detail = w.get("detail", "")
                    if "TRICK_ROOM_MAY_HELP_OPPONENT" in code or "DUAL" in code or "BACKUP" in code or "FAST_MON" in code:
                        rejected.append(f"`{code}` — {detail}")
                if rejected:
                    lines.append("")
                    lines.append("**Rejected / conditional lines:**")
                    for rj in rejected[:4]:
                        lines.append(f"- {rj}")
            lines.append("")
        if lp.get("candidate_leads"):
            lines.append("## 🎮 Lead simulation lite")
            for cand in lp.get("candidate_leads", [])[:3]:
                lead = " + ".join(cand.get("lead", []))
                lines.append(f"### {lead} — {cand.get('verdict','candidate lead')}")
                lines.append(f"- **Plan:** {cand.get('plan','')}")
                if cand.get("turn_1"):
                    lines.append(f"- **T1:** {' / '.join(cand.get('turn_1', []))}")
                if cand.get("turn_2"):
                    lines.append(f"- **T2:** {' / '.join(cand.get('turn_2', []))}")
                if cand.get("good_into"):
                    lines.append(f"- **Good into:** {cand.get('good_into')}")
                if cand.get("risk"):
                    lines.append(f"- **Risk:** {cand.get('risk')}")
            lines.append("")
        lines.append("## ⚔️ Detailed sets")
        if ascii_ok and markdown_card:
            lines.append("_Card view: inline Pokémon ASCII cards printed directly in chat. Item ASCII is intentionally omitted._")
            lines.append("")
        for block in render.get("set_note_blocks", []):
            title = f"### {block['slot']}) {block['pokemon']}"
            if block.get("item"):
                title += f" @ {block['item']}"
            if block.get("ability"):
                title += f" — {block['ability']}"
            lines.append(title)
            pokemon_ascii = _trim_ascii_for_card((block.get("pokemon_ascii_asset") or {}).get("text", ""))
            if ascii_ok and markdown_card and pokemon_ascii:
                lines.append("```text")
                lines.append(pokemon_ascii)
                lines.append("```")
            type_line = ""
            # type is stored on team table row, so find it by slot for the detailed card.
            trow = next((r for r in render.get("team_table_rows", []) if r.get("slot") == block.get("slot")), {})
            type_line = trow.get("type", "")
            item_part = block.get("item", "")
            ability_part = block.get("ability", "")
            if type_line or item_part or ability_part:
                parts = [p for p in [type_line, item_part, ability_part] if p]
                lines.append("**" + " · ".join(parts) + "**")
            if block.get("role"):
                lines.append(f"**Role:** {block['role']}")
            if block.get("item_source") or block.get("spread_source") or block.get("speed_role"):
                fit_bits = []
                if block.get("item_source"):
                    fit_bits.append(f"Item source: `{block.get('item_source')}`")
                if block.get("spread_source"):
                    fit_bits.append(f"Spread source: `{block.get('spread_source')}`")
                if block.get("speed_role"):
                    fit_bits.append(f"Speed role: `{block.get('speed_role')}`")
                lines.append("**Fit:** " + " · ".join(fit_bits))
            if block.get("nature"):
                lines.append(f"**Nature:** {block.get('nature','')}")
            if block.get("spread_display"):
                lines.append(f"**Investment:** {block.get('spread_display','')} — **Total {block.get('spread_total','')}**")
            stats_disp = block.get("displayed_stats_display", {}) or {}
            if stats_disp.get("compact"):
                stat_src = f" _(stat source: `{block.get('stat_source')}`)_" if block.get("stat_source") else ""
                lines.append(f"**Final stats:** {stats_disp.get('compact')}{stat_src}")
            if block.get("move_list"):
                lines.append(f"**Moves:** {_moves_as_chips(block.get('move_list', []))}")
            if block.get("spread_reason"):
                lines.append("**Why this spread:**")
                for reason in block.get("spread_reason", []):
                    lines.append(f"- {reason}")
            sf = block.get("spread_fit") or {}
            if sf.get("meta_baseline"):
                mb = sf.get("meta_baseline", {})
                mb_disp = (mb.get("spread_display") or {}).get("verbose", "")
                usage = f"; usage {mb.get('usage')}" if mb.get("usage") else ""
                lines.append(f"**Meta baseline:** {mb.get('nature','')} {mb_disp} (`{mb.get('source_label','META_SPREAD_DIRECT')}`{usage})")
                if sf.get("decision") and sf.get("decision") != "USE_META_BASELINE":
                    lines.append(f"**Spread decision:** {sf.get('decision')} — diff `{sf.get('diff', {})}`; speed tradeoff `{sf.get('speed_tradeoff', {})}`")
            lines.append("")
            lines.append("---")
            lines.append("")
    if render.get("ally_safety_matrices"):
        lines.append("## 🧯 Spread-move ally safety")
        for matrix in render.get("ally_safety_matrices", []):
            lines.append(f"### {matrix.get('user')} — {matrix.get('move')}")
            lines.append("| Partner | Type | Safe? | Reason |")
            lines.append("|---|---|---:|---|")
            for row in matrix.get("rows", []):
                lines.append(f"| {row.get('partner')} | {row.get('partner_types')} | {row.get('safe')} | {row.get('reason')} |")
            lines.append("")
    if render.get("meta_threat_fit", {}).get("threats_checked"):
        lines.append("## 🧠 Mechanic interaction / meta threat fit")
        lines.append("| Meta threat | Team answer | Verified interaction | Remaining risk |")
        lines.append("|---|---|---|---|")
        for row in render.get("meta_threat_fit", {}).get("threats_checked", []):
            lines.append(f"| {row.get('threat','')} | {row.get('team_answer','')} | {row.get('interaction_status','')} | {row.get('remaining_risk','')} |")
        lines.append("")

    if render.get("mechanic_interactions"):
        lines.append("## 🧩 Interaction receipts")
        lines.append("| Interaction | Result | Team implication |")
        lines.append("|---|---|---|")
        for row in render.get("mechanic_interactions", []):
            lines.append(f"| {row.get('interaction','')} | {row.get('status','')} | {row.get('team_implication','')} |")
        lines.append("")

    if render.get("warnings"):
        lines.append("## ⚠️ Main risks / verifier warnings")
        lines.append("| Code | Detail |")
        lines.append("|---|---|")
        for w in render["warnings"]:
            lines.append(f"| {w.get('code','WARN')} | {w.get('detail','')} |")
        lines.append("")
    if receipt.get("team_ok") and compact and style not in {"no-ascii", "no-card"}:
        if is_claude_platform:
            lines.append("ต้องการให้ผมแสดงเป็น Claude HTML team card ผ่าน widget แบบที่ส่งตัวอย่างไว้ไหม?")
        else:
            lines.append("ต้องการให้ผมแสดงเป็น inline ASCII team card ไหม?")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


TYPE_CLAIM_WORD_RE = re.compile(
    r"\b(immune|immunity|resist(?:ed|s|ance)?|super\s*effective|not\s+very\s+effective|neutral|weak(?:ness)?|0\s*x|0\.5\s*x|1\s*x|2\s*x|4\s*x)\b|ไม่ได้ผล|ไม่โดน|ต้าน|ครึ่ง|สองเท่า|สี่เท่า|แพ้ทาง|โดนแรง|เบามาก|ปกติ",
    re.I,
)
_TYPE_TOKEN_RE = re.compile(r"\b(" + "|".join(re.escape(_TYPE_NAME[t]) for t in VALID_TYPES) + r")\b", re.I)


def _collect_typechart_receipts(obj):
    """Collect nested verify_type_effectiveness receipts from any verifier payload."""
    out = []
    seen = set()
    def walk(x):
        if isinstance(x, dict):
            if x.get("entity") == "type_effectiveness" and x.get("status") == "pass":
                key = json.dumps({
                    "atk": x.get("attacking_type"),
                    "def": x.get("defender_types"),
                    "mult": x.get("total_type_multiplier"),
                    "label": x.get("label"),
                }, sort_keys=True, ensure_ascii=False)
                if key not in seen:
                    seen.add(key); out.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(obj)
    return out


def _line_type_claims(answer_text: str):
    """Return public lines that contain type-effectiveness-style claims."""
    claims = []
    for i, line in enumerate(str(answer_text or "").splitlines(), start=1):
        if TYPE_CLAIM_WORD_RE.search(line):
            # Avoid false positives from section names that do not make effectiveness claims.
            if re.search(r"typechart receipt|No typechart receipt|type claim|type-effectiveness receipt", line, re.I):
                continue
            claims.append({"line": i, "text": line.strip()[:260]})
    return claims


def _known_type_regression_failures(answer_text: str):
    """Hard-coded regression traps for previously observed typechart mistakes.

    These are not a replacement for receipts; they catch dangerous wording even
    when the final answer contains some unrelated typechart receipt.
    """
    failures = []
    text = str(answer_text or "")
    line_items = list(enumerate(text.splitlines(), start=1))
    patterns = [
        (re.compile(r"(?i)(ghost|👻).*(dark|🌑).*(immune|0\s*x|ไม่ได้ผล|ไม่โดน)|(dark|🌑).*(ghost|👻).*(immune|0\s*x|ไม่ได้ผล|ไม่โดน)"),
         "FAIL_TYPECHART_REGRESSION_GHOST_DARK_IMMUNE", "Ghost → Dark is 0.5x resisted, not immune."),
        (re.compile(r"(?i)(fire|🔥).*(steel\s*/\s*dragon|steel.*dragon|⚙️.*🐉).*(2\s*x|super\s*effective|สองเท่า|แพ้ทาง)|(steel\s*/\s*dragon|steel.*dragon|⚙️.*🐉).*(fire|🔥).*(2\s*x|super\s*effective|สองเท่า|แพ้ทาง)"),
         "FAIL_TYPECHART_REGRESSION_FIRE_STEEL_DRAGON_2X", "Fire → Steel/Dragon is 1x neutral after dual-type multiplication."),
        (re.compile(r"(?i)(fighting|🤜).*(steel\s*/\s*dragon|steel.*dragon|⚙️.*🐉|Archaludon).*(4\s*x|4x|สี่เท่า)|(steel\s*/\s*dragon|steel.*dragon|⚙️.*🐉|Archaludon).*(fighting|🤜).*(4\s*x|4x|สี่เท่า)"),
         "FAIL_TYPECHART_REGRESSION_FIGHTING_STEEL_DRAGON_4X", "Fighting → Steel/Dragon is 2x super-effective, not 4x."),
    ]
    for line_no, line in line_items:
        for rgx, code, detail in patterns:
            if rgx.search(line):
                failures.append({"code": code, "line": line_no, "detail": detail, "text": line.strip()[:260]})
    return failures


def _type_claim_guard(answer_text: str, receipt: dict):
    """Validate that public type-effectiveness claims are backed by receipts."""
    claims = _line_type_claims(answer_text)
    type_receipts = _collect_typechart_receipts(receipt)
    failures = _known_type_regression_failures(answer_text)
    warnings = []
    if claims and not type_receipts:
        failures.append({
            "code": "FAIL_TYPE_CLAIM_WITHOUT_TYPECHART_RECEIPT",
            "detail": "Public type effectiveness claims require verify.py typechart/damage typechart receipt. Do not infer immune/resist/weak/neutral from memory.",
            "claim_lines": claims[:8],
        })
    elif claims and type_receipts:
        # If a line mentions an explicit attack+defender type pair and a multiplier/label, require a matching receipt display somewhere in the answer or receipt.
        displays = "\n".join(str(r.get("display", "")) for r in type_receipts)
        for c in claims:
            line = c["text"]
            types = [m.group(1).lower() for m in _TYPE_TOKEN_RE.finditer(line)]
            has_numeric = re.search(r"\b(?:0|0\.5|1|2|4)\s*x\b", line, re.I)
            if len(set(types)) >= 2 and has_numeric and not any(str(r.get("display", "")).lower() in line.lower() for r in type_receipts):
                # Keep as warning because public prose may paraphrase receipts, but force audit visibility.
                warnings.append({
                    "code": "WARN_TYPE_CLAIM_PARAPHRASED_NOT_COPIED_FROM_RECEIPT",
                    "line": c["line"],
                    "detail": "Prefer copying type receipt display exactly, e.g. 'Ghost → Dark = 0.5x resisted'.",
                    "text": line,
                    "available_receipts": [r.get("display") for r in type_receipts[:6]],
                })
    return failures, warnings


EXTERNAL_POKEMON_BLOCKLIST = {
    "amoonguss", "urshifu", "urshifurapidstrike", "urshifusinglestrike",
    "fluttermane", "rillaboom", "landorus", "tornadus", "ogerpon",
    "calyrex", "miraidon", "koraidon", "ironhands", "greattusk",
}

ENTITY_STOP_NAMES = {
    "pokemon", "champions", "ranked", "team", "meta", "source", "pass", "fail",
    "protect", "tailwind", "trick room", "fake out", "wide guard", "follow me", "counter",
}


def _all_local_entity_names() -> dict:
    """Local positive-whitelist name index used by public entity lint."""
    pokemon = set(load_01_pokemon()["name"].dropna().astype(str).tolist())
    moves = set(load_05_07_moves()["move_name"].dropna().astype(str).tolist())
    g = load_08_global()
    items = set(g[g["entity_type"].str.lower() == "item"]["name"].dropna().astype(str).tolist())
    abilities = set()
    for text in load_01_pokemon()["abilities"].dropna().astype(str).tolist():
        for a in text.split(";"):
            if a.strip():
                abilities.add(a.strip())
    abilities.update(g[g["entity_type"].str.lower() == "ability"]["name"].dropna().astype(str).tolist())
    return {"pokemon": pokemon, "move": moves, "item": items, "ability": abilities}


def _collect_verified_entities_from_receipt(receipt: dict) -> dict:
    out = {"pokemon": set(), "move": set(), "ability": set(), "item": set(), "mechanic": set(), "boardscan": False, "interaction": False, "counterroute": False, "selfaudit": False, "typepassive": False}
    def add(kind, val):
        if val:
            out[kind].add(normalize_id(str(val)))
    def walk(x):
        if isinstance(x, dict):
            ent = x.get("entity", "")
            status = str(x.get("status", "")).lower()
            if ent == "pokemon" and status == "pass":
                add("pokemon", x.get("name")); add("pokemon", x.get("id")); add("pokemon", x.get("query"))
            elif ent == "move" and status == "pass":
                add("move", x.get("move_name")); add("move", x.get("name")); add("move", x.get("move_id")); add("move", x.get("id")); add("move", x.get("query"))
            elif ent == "ability" and status == "pass":
                add("ability", x.get("ability_name")); add("ability", x.get("name")); add("ability", x.get("ability_id")); add("ability", x.get("id")); add("ability", x.get("query"))
            elif ent == "item" and status == "pass":
                add("item", x.get("name")); add("item", x.get("id")); add("item", x.get("query"))
            elif ent in {"mechanic_interaction", "mechanic_matrix"} and status in {"pass", "pass_blocked", "pass_with_warnings"}:
                out["interaction"] = True
                actor = x.get("actor", {}) or {}
                add("pokemon", actor.get("pokemon")); add("move", actor.get("move")); add("ability", actor.get("ability"))
                if x.get("blocked_by"):
                    add("ability", x.get("blocked_by"))
                if x.get("blocked_by_pokemon"):
                    add("pokemon", x.get("blocked_by_pokemon"))
            elif x.get("mode") == "board_scan" and status in {"pass", "pass_with_warnings"}:
                out["boardscan"] = True
                add("pokemon", x.get("attacker")); add("move", x.get("move"))
            elif ent == "typepassive" and status in {"pass", "pass_blocked", "pass_with_warnings"}:
                out["typepassive"] = True
            elif ent == "counter_route_receipt" and status in {"pass", "pass_with_warnings"}:
                out["counterroute"] = True
                add("pokemon", x.get("candidate")); add("pokemon", x.get("threat"))
            elif x.get("mode") == "final_self_audit" and status == "pass":
                out["selfaudit"] = True
            elif ent == "mechanic" and status == "pass":
                add("mechanic", x.get("name")); add("mechanic", x.get("id"))
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(receipt)
    return out


def _find_name_lines(answer_text: str, names: set) -> list:
    """Find exact local names in public text. Avoid very short names to reduce noise."""
    lines = str(answer_text or "").splitlines()
    hits = []
    # Prefer longer names first so Rapid Strike / Farigiraf-style phrases are found sensibly.
    for name in sorted(names, key=lambda n: len(str(n)), reverse=True):
        nm = str(name).strip()
        if not nm or normalize_id(nm) in ENTITY_STOP_NAMES:
            continue
        if len(nm) < 5 and " " not in nm:
            continue
        pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(nm) + r"(?![A-Za-z0-9])", re.I)
        for i, line in enumerate(lines, start=1):
            if pat.search(line):
                hits.append({"name": nm, "line": i, "text": line.strip()[:260]})
    return hits


def _public_entity_guard(answer_text: str, receipt: dict):
    failures = []
    warnings = []
    text = str(answer_text or "")
    local = _all_local_entity_names()
    verified = _collect_verified_entities_from_receipt(receipt or {})
    # Hard block known mainline/VGC memory leakage names when absent from 01.
    for leak in sorted(EXTERNAL_POKEMON_BLOCKLIST):
        if leak in {normalize_id(n) for n in local["pokemon"]}:
            continue
        display = leak
        # allow common space/hyphen variants
        pretty = re.sub(r"(rapidstrike|singlestrike)$", r" \1", leak)
        pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(display) + r"(?![A-Za-z0-9])|" + re.escape(pretty).replace("\\ ", r"[\s\-]+"), re.I)
        for i, line in enumerate(text.splitlines(), start=1):
            if pat.search(normalize_id(line)) or pat.search(line):
                failures.append({"code": "FAIL_PUBLIC_POKEMON_NOT_IN_01", "line": i, "entity": display, "detail": "Named Pokémon is not in local 01 whitelist; use a generic threat category instead.", "text": line.strip()[:260]})
    # Local-but-unreceipted names are not allowed in final public claims.
    for kind, code in [("pokemon", "FAIL_PUBLIC_POKEMON_WITHOUT_RECEIPT"), ("move", "FAIL_PUBLIC_MOVE_NOT_VERIFIED"), ("ability", "FAIL_PUBLIC_ABILITY_NOT_VERIFIED"), ("item", "FAIL_PUBLIC_ITEM_NOT_VERIFIED")]:
        for hit in _find_name_lines(text, local[kind]):
            nid = normalize_id(hit["name"])
            if nid in verified.get(kind, set()):
                continue
            # Avoid failing source/file names or generic policy text.
            if re.search(r"receipt|source|whitelist|local|No .* receipt|gate|FAIL_|WARN_|rule", hit["text"], re.I):
                continue
            failures.append({"code": code, "line": hit["line"], "entity": hit["name"], "detail": f"Public {kind} name appears without a matching local verifier receipt.", "text": hit["text"]})
    # Unknown capitalized entity warning in risk/threat sections; hard names should be handled above.
    in_risk = False
    for i, line in enumerate(text.splitlines(), start=1):
        if re.match(r"^#+\s+.*(risk|threat|matchup|ความเสี่ยง|เมต้า|ภัย)", line, re.I):
            in_risk = True
            continue
        if re.match(r"^#+\s+", line):
            in_risk = False
        if in_risk:
            caps = re.findall(r"\b[A-Z][a-z]{4,}(?:[-\s][A-Z][a-z]{3,})?\b", line)
            for c in caps:
                if normalize_id(c) not in {normalize_id(n) for vals in local.values() for n in vals} and normalize_id(c) not in ENTITY_STOP_NAMES:
                    warnings.append({"code": "WARN_UNKNOWN_CAPITALIZED_ENTITY", "line": i, "entity": c, "detail": "Risk/threat section contains an unknown capitalized term; verify or replace with generic category.", "text": line.strip()[:260]})
    return failures, warnings



TYPE_PASSIVE_CLAIM_PATTERNS = [
    (re.compile(r"(?i)(Grass|หญ้า).*(Leech\s+Seed|powder|spore|สปอร์|ผง|Effect\s+Spore|กัน|immune|ไม่โดน)"), "FAIL_TYPE_PASSIVE_CLAIM_WITHOUT_RECEIPT"),
    (re.compile(r"(?i)(Fire|ไฟ).*(burn|burned|เผาไหม้|ไหม้|กัน|immune|ไม่ติด)"), "FAIL_STATUS_IMMUNITY_CLAIM_WITHOUT_TYPEPASSIVE_RECEIPT"),
    (re.compile(r"(?i)(Electric|ไฟฟ้า).*(paraly|อัมพาต|กัน|immune|ไม่ติด)"), "FAIL_STATUS_IMMUNITY_CLAIM_WITHOUT_TYPEPASSIVE_RECEIPT"),
    (re.compile(r"(?i)(Ground|ดิน).*(Thunder\s+Wave|อัมพาต|paraly|กัน|immune|ไม่โดน)"), "FAIL_THUNDER_WAVE_GROUND_CLAIM_WITHOUT_RECEIPT"),
    (re.compile(r"(?i)(Flying|บิน|ungrounded|ลอย).*(Spikes|Toxic\s+Spikes|Sticky\s+Web|hazard|ไม่โดน|กัน)"), "FAIL_FIELD_HAZARD_IMMUNITY_CLAIM_WITHOUT_RECEIPT"),
    (re.compile(r"(?i)(Rock|หิน).*(Sandstorm|sand|พายุทราย).*(Sp\.?\s*Def|special defense|50%|1\.5|boost|เพิ่ม|ไม่โดน|chip)"), "FAIL_WEATHER_STAT_BOOST_CLAIM_WITHOUT_RECEIPT"),
    (re.compile(r"(?i)(Rock|Ground|Steel|หิน|ดิน|เหล็ก).*(Sandstorm|sand|พายุทราย).*(ไม่โดน|no chip|immune|damage)"), "FAIL_TYPE_PASSIVE_CLAIM_WITHOUT_RECEIPT"),
    (re.compile(r"(?i)(Poison|Steel|พิษ|เหล็ก).*(poison|badly poisoned|toxic|ติดพิษ|พิษรุนแรง|Corrosion|กัน|immune|ไม่ติด)"), "FAIL_STATUS_IMMUNITY_CLAIM_WITHOUT_TYPEPASSIVE_RECEIPT"),
    (re.compile(r"(?i)(Poison|พิษ).*(Toxic\s+Spikes|ลบ|remove|clear).*(grounded|switch|เข้า|สนาม)?"), "FAIL_FIELD_HAZARD_IMMUNITY_CLAIM_WITHOUT_RECEIPT"),
    (re.compile(r"(?i)(Ice|น้ำแข็ง).*(freeze|frozen|แช่แข็ง|Snow|หิมะ|Defense|Def|1\.5|50%|Hail|hail|กัน|immune|ไม่โดน)"), "FAIL_TYPE_PASSIVE_CLAIM_WITHOUT_RECEIPT"),
    (re.compile(r"(?i)(Ghost|ผี).*(trap|trapping|escape|flee|switch|Mean\s+Look|Shadow\s+Tag|Arena\s+Trap|หนี|สลับ|กัก|จับ)"), "FAIL_TRAPPING_GHOST_CLAIM_WITHOUT_RECEIPT"),
    (re.compile(r"(?i)(Dark|มืด).*(Prankster|priority.*status|status.*priority|Taunt|Encore|Thunder\s+Wave|กัน|immune|บล็อก)"), "FAIL_PRANKSTER_DARK_CLAIM_WITHOUT_RECEIPT"),
]


def _typepassive_claim_guard(answer_text: str, receipt: dict):
    failures = []
    warnings = []
    verified = _collect_verified_entities_from_receipt(receipt or {})
    for i, line in enumerate(str(answer_text or "").splitlines(), start=1):
        if re.search(r"typepassive receipt|type passive receipt|09_type_passive|No typepassive receipt", line, re.I):
            continue
        for rgx, code in TYPE_PASSIVE_CLAIM_PATTERNS:
            if rgx.search(line) and not verified.get("typepassive"):
                failures.append({"code": code, "line": i, "detail": "Type passive/status/weather/hazard claims require verify.py typepassive receipt. Typechart receipt alone is not enough.", "text": line.strip()[:260]})
    return failures, warnings

MECHANIC_CLAIM_PATTERNS = [
    (re.compile(r"(?i)(bypass(?:es)?|ignore(?:s)?|through|pierce(?:s)?|ฝ่า|ไม่สน|ทะลุ).*Protect|Protect.*(bypass|ignore|ฝ่า|ไม่สน|ทะลุ)"), "FAIL_PROTECT_BYPASS_CLAIM_WITHOUT_LOCAL_MECHANIC"),
    (re.compile(r"(?i)(Soundproof|sound\s*move|Boomburst|Clanging\s+Scales|Hyper\s+Voice).*(block|immune|0\s*damage|บล็อก|กัน|ไม่ได้ผล|ไม่โดน)"), "FAIL_ABILITY_INTERACTION_CLAIM_WITHOUT_RECEIPT"),
    (re.compile(r"(?i)(ally\s+damage|hits?\s+ally|โดนเพื่อน|ตีเพื่อน|spread\s+move|Earthquake.*ally|Boomburst.*ally)"), "FAIL_MECHANIC_CLAIM_WITHOUT_BOARDSCAN_RECEIPT"),
    (re.compile(r"(?i)(Wide\s+Guard|redirection|Rage\s+Powder|Follow\s+Me).*(block|ignore|redirect|บล็อก|กัน|ล่อ|เปลี่ยนเป้า)"), "FAIL_MECHANIC_CLAIM_WITHOUT_RECEIPT"),
    (re.compile(r"(?i)(White\s+Herb|Mental\s+Herb|Focus\s+Sash).*(cure|block|reset|กัน|ล้าง|แก้)"), "FAIL_ITEM_MECHANIC_CLAIM_WITHOUT_RECEIPT"),
    (re.compile(r"(?i)(Mummy|Wandering\s+Spirit).*(Contrary|ability|contact|สลับ|เปลี่ยน|ลบ|ขโมย)"), "FAIL_ABILITY_INTERACTION_WITHOUT_INTERACTION_RECEIPT"),
    (re.compile(r"(?i)(Intimidate|Defiant|Contrary).*(Intimidate|Defiant|Contrary|lower|boost|กลับ|เพิ่ม|ลด)"), "FAIL_ABILITY_INTERACTION_WITHOUT_INTERACTION_RECEIPT"),
    (re.compile(r"(?i)(Thunder\s+Wave).*(Contrary|stat|paraly|ไม่กลับ|กลับ)"), "FAIL_STATUS_MECHANIC_CLAIM_WITHOUT_RECEIPT"),
    (re.compile(r"(?i)(King[’']?s\s+Shield).*(Contrary|Attack|contact|lower|boost|ลด|เพิ่ม)"), "FAIL_ABILITY_INTERACTION_WITHOUT_INTERACTION_RECEIPT"),
    (re.compile(r"(?i)(Gale\s+Wings).*(priority|Brave\s+Bird|Flying|\+1|ก่อน)"), "FAIL_PRIORITY_MODIFIER_CLAIM_WITHOUT_RECEIPT"),
    (re.compile(r"(?i)(No\s+Guard).*(accuracy|miss|100%|ไม่\s*miss|แม่น)"), "FAIL_ACCURACY_MECHANIC_CLAIM_WITHOUT_RECEIPT"),
    (re.compile(r"(?i)(Electric\s+Surge|Electric\s+Terrain).*(1\.5|50%|boost|power|Thunderbolt|แรงขึ้น)"), "FAIL_FIELD_MECHANIC_CLAIM_WITHOUT_RECEIPT"),
    (re.compile(r"(?i)(Pixilate).*(Hyper\s+Voice|Normal.*Fairy|Fairy.*sound|เปลี่ยน.*Fairy)"), "FAIL_TYPE_CHANGE_CLAIM_WITHOUT_RECEIPT"),
    (re.compile(r"(?i)(burn|burned|เผาไหม้).*(Atk|Attack|physical|50%|half|ครึ่ง)"), "FAIL_STATUS_MECHANIC_CLAIM_WITHOUT_RECEIPT"),
    (re.compile(r"(?i)(Snow|Snowscape|Aurora\s+Veil).*(Defense|Def|Ice|1\.5|ลดดาเมจ|snowing|หิมะ)"), "FAIL_FIELD_MECHANIC_CLAIM_WITHOUT_RECEIPT"),
]

COUNTER_CLAIM_PATTERN = re.compile(r"(?i)(hard\s*counter|hard\s*check|best\s*(?:answer|counter)|guaranteed\s*answer|แก้ขาด|เคาน์เตอร์ขาด|รับได้หมด|ชนะชัวร์|แก้ได้แน่นอน)")
FORM_AMBIGUITY_PATTERN = re.compile(r"(?i)Mega\s+Raichu(?!\s*[XY])")


def _mechanic_claim_guard(answer_text: str, receipt: dict):
    failures = []
    warnings = []
    verified = _collect_verified_entities_from_receipt(receipt or {})
    has_mech = bool(verified.get("interaction") or verified.get("boardscan") or verified.get("mechanic"))
    for i, line in enumerate(str(answer_text or "").splitlines(), start=1):
        if FORM_AMBIGUITY_PATTERN.search(line) and re.search(r"(?i)(Electric\s+Surge|No\s+Guard|ability|Thunderbolt|terrain|accuracy|miss)", line):
            failures.append({"code": "WARN_FORM_AMBIGUOUS_MEGA_RAICHU_X_Y", "line": i, "detail": "Mega Raichu form-specific mechanics require Mega Raichu X/Y, not generic Mega Raichu.", "text": line.strip()[:260]})
        for rgx, code in MECHANIC_CLAIM_PATTERNS:
            if rgx.search(line):
                if code.endswith("BOARDSCAN_RECEIPT") and not verified.get("boardscan"):
                    failures.append({"code": code, "line": i, "detail": "Move-target/ally-damage claims require verify.py boardscan receipt.", "text": line.strip()[:260]})
                elif code == "FAIL_PROTECT_BYPASS_CLAIM_WITHOUT_LOCAL_MECHANIC":
                    failures.append({"code": code, "line": i, "detail": "Protect bypass claims require an explicit local mechanic receipt; do not import mainline memory.", "text": line.strip()[:260]})
                elif not has_mech:
                    failures.append({"code": code, "line": i, "detail": "Mechanic/ability/status/field/item interaction claim requires verify.py interaction, mechanic, boardscan, damage, or counterroute receipt. Entity existence alone is not enough.", "text": line.strip()[:260]})
    for i, line in enumerate(str(answer_text or "").splitlines(), start=1):
        if COUNTER_CLAIM_PATTERN.search(line) and not verified.get("counterroute"):
            failures.append({"code": "FAIL_COUNTER_RANK_WITHOUT_ROUTE_RECEIPTS", "line": i, "detail": "Hard counter/check/best-answer claims require verify.py counterroute receipt with type/speed/priority/interaction/damage route.", "text": line.strip()[:260]})
    return failures, warnings


def _base_stat_claim_guard(answer_text: str, receipt: dict):
    failures = []
    warnings = []
    df = load_01_pokemon()
    verified = _collect_verified_entities_from_receipt(receipt or {})
    stat_alias = {"hp":"hp", "atk":"atk", "attack":"atk", "def":"def", "defense":"def", "spa":"spa", "sp.atk":"spa", "special attack":"spa", "spd":"spd", "sp.def":"spd", "special defense":"spd", "spe":"spe", "speed":"spe"}
    stat_pat = re.compile(r"(?i)base\s+(HP|Atk|Attack|Def|Defense|SpA|Sp\.Atk|Special Attack|SpD|Sp\.Def|Special Defense|Spe|Speed)\s*(?:=|:|is)?\s*(\d{1,3})")
    for i, line in enumerate(str(answer_text or "").splitlines(), start=1):
        m = stat_pat.search(line)
        if not m:
            continue
        stat_key = stat_alias.get(m.group(1).lower(), "")
        val = int(m.group(2))
        matched_pokemon = None
        for _, row in df.iterrows():
            nm = str(row["name"])
            if re.search(r"(?<![A-Za-z0-9])" + re.escape(nm) + r"(?![A-Za-z0-9])", line, re.I):
                matched_pokemon = row
                break
        if matched_pokemon is None:
            failures.append({"code": "FAIL_BASE_STAT_CLAIM_WITHOUT_01_RECEIPT", "line": i, "detail": "Base stat number appears without a local Pokémon row receipt.", "text": line.strip()[:260]})
            continue
        expected = int(matched_pokemon[stat_key])
        pname = matched_pokemon["name"]
        if val != expected:
            failures.append({"code": "FAIL_BASE_STAT_CLAIM_CONFLICTS_01", "line": i, "pokemon": pname, "stat": stat_key, "claimed": val, "expected": expected, "source": "01", "text": line.strip()[:260]})
        elif normalize_id(pname) not in verified.get("pokemon", set()):
            failures.append({"code": "FAIL_BASE_STAT_CLAIM_WITHOUT_01_RECEIPT", "line": i, "pokemon": pname, "detail": "Base stat claim must be tied to a local Pokémon receipt.", "text": line.strip()[:260]})
    return failures, warnings



def _semantic_stat_adjective_guard(answer_text: str, receipt: dict):
    failures = []
    warnings = []
    if (receipt or {}).get("mode") != "full_team_verification":
        return failures, warnings
    slots = []
    for r in (receipt.get("sets", []) or []):
        name = _slot_display_name_from_receipt(r)
        base = _base_stats_from_set_receipt(r)
        profile = _bulk_profile_from_base_stats(base)
        stats = r.get("displayed_stats", {}).get("displayed_stats", {}) or {}
        slots.append({"name": name, "base": base, "profile": profile, "displayed": stats})
    for i, line in enumerate(str(answer_text or "").splitlines(), start=1):
        if re.search(r"receipt|FAIL_|WARN_|gate|rule|typechart|threataudit|stat\s+receipt", line, re.I):
            continue
        if not STAT_ADJECTIVE_PATTERN.search(line):
            continue
        for sl in slots:
            nm = str(sl["name"])
            if not nm or not re.search(r"(?<![A-Za-z0-9])" + re.escape(nm) + r"(?![A-Za-z0-9])", line, re.I):
                continue
            has_stat_evidence = bool(STAT_RECEIPT_WORD_PATTERN.search(line))
            if not has_stat_evidence:
                code = "FAIL_SPEED_CLAIM_WITHOUT_SPEED_RECEIPT" if re.search(r"(?i)(เร็ว|ช้า|fast|slow)", line) else "FAIL_STAT_ADJECTIVE_WITHOUT_STAT_RECEIPT"
                failures.append({"code": code, "line": i, "pokemon": nm, "detail": "Public stat adjective must quote base/displayed stats from receipt, not impression or mainline memory.", "text": line.strip()[:260]})
            if TWO_SIDED_BULK_PATTERN.search(line) and not sl["profile"].get("mixed_bulk_ok"):
                failures.append({"code": "FAIL_BULK_CLAIM_CONFLICTS_BASE_STATS", "line": i, "pokemon": nm, "base_stats": sl["base"], "detail": sl["profile"].get("summary"), "text": line.strip()[:260]})
    return failures, warnings


def _verified_move_ability_names(receipt: dict) -> list[tuple[str, str]]:
    names = []
    for r in (receipt or {}).get("sets", []) or []:
        ab = r.get("ability", {}) or {}
        if ab.get("status") == "pass":
            names.append((ab.get("ability_name", ab.get("name", "")), "ability"))
        for m in r.get("moves", []) or []:
            if m.get("status") == "pass":
                names.append((m.get("move_name", m.get("name", "")), "move"))
    # extra local names often mentioned in explanation even when not slotted
    return [(n, k) for n, k in names if n]


def _mechanic_overinterpret_guard(answer_text: str, receipt: dict):
    failures = []
    warnings = []
    verified = _collect_verified_entities_from_receipt(receipt or {})
    mechanic_ids = verified.get("mechanic", set()) or set()
    names = _verified_move_ability_names(receipt if isinstance(receipt, dict) else {})
    # Also catch the two repeated hallucination examples globally when named.
    names.extend([("Stamina", "ability"), ("Electro Shot", "move")])
    seen = set(); uniq = []
    for n, k in names:
        key = normalize_id(n)
        if key and key not in seen:
            seen.add(key); uniq.append((n, k, key))
    for i, line in enumerate(str(answer_text or "").splitlines(), start=1):
        if re.search(r"FAIL_|WARN_|No mechanic receipt|mechanic receipt", line, re.I):
            continue
        for name, kind, nid in uniq:
            if not re.search(r"(?<![A-Za-z0-9])" + re.escape(name) + r"(?![A-Za-z0-9])", line, re.I):
                continue
            has_exact_mech = nid in mechanic_ids
            if MECHANIC_STAGE_CLAIM_PATTERN.search(line):
                if DESCRIPTION_08_CAVEAT_PATTERN.search(line):
                    failures.append({"code": "FAIL_08_DESCRIPTION_OVERINTERPRETED", "line": i, "entity": name, "detail": "08 description may be quoted/paraphrased, but do not add exact stat stages such as +1 unless mechanic receipt confirms it.", "text": line.strip()[:260]})
                elif not has_exact_mech:
                    failures.append({"code": "FAIL_MECHANIC_STAGE_CLAIM_WITHOUT_RECEIPT", "line": i, "entity": name, "entity_kind": kind, "detail": "Stat-stage/mechanic-stage claims require verify.py mechanic/interaction receipt for that exact entity; local move/ability existence is not enough.", "text": line.strip()[:260]})
            elif MOVE_SEQUENCE_CLAIM_PATTERN.search(line) and not DESCRIPTION_08_CAVEAT_PATTERN.search(line) and not has_exact_mech:
                failures.append({"code": "FAIL_MOVE_SEQUENCE_CLAIM_WITHOUT_MECHANIC_RECEIPT", "line": i, "entity": name, "entity_kind": kind, "detail": "Move/ability sequence claims require mechanic/interaction receipt or must be explicitly labelled as 08 description.", "text": line.strip()[:260]})
    return failures, warnings


def _semantic_audit_presence_guard(answer_text: str, receipt: dict):
    failures = []
    warnings = []
    if (receipt or {}).get("mode") != "full_team_verification":
        return failures, warnings
    gates = (receipt.get("team_gates", {}) or {})
    has_threat = gates.get("threat_audit", {}).get("entity") == "threat_audit_receipt" and gates.get("threat_audit", {}).get("status") in {"pass", "pass_with_warnings"}
    has_itemfit = gates.get("item_threat_fit", {}).get("entity") == "item_threat_fit_receipt" and gates.get("item_threat_fit", {}).get("status") in {"pass", "pass_with_warnings"}
    risk_claim = re.search(r"(?i)(risk|threat|จุดอ่อน|แพ้ทาง|weakness|resist|immune|berry|Chople|Shuca|ลดดาเมจ|โดนเพื่อน|Earthquake|item reason|เหตุผลไอเท็ม)", answer_text or "")
    if risk_claim and not has_threat:
        failures.append({"code": "FAIL_RISK_SECTION_WITHOUT_THREAT_AUDIT", "detail": "Risk/item/weakness prose requires verify.py threataudit receipt. lint-output is not semantic verification."})
    if re.search(r"(?i)(Berry|Chople|Shuca|Occa|Passho|Yache|Roseli|ลด.*super|ลด.*แพ้ทาง|resist berry)", answer_text or "") and not has_itemfit:
        failures.append({"code": "FAIL_ITEM_REASON_WITHOUT_ITEMTHREATFIT_RECEIPT", "detail": "Defensive berry/item reasoning requires verify.py itemthreatfit receipt."})
    return failures, warnings

_PUBLIC_TYPE_EMOJIS = "⚪🔥💧⚡🌿🧊🤜☠️🟤🪽🔮🐞🪨👻🐉🌑⚙️🧚"

def lint_public_output(answer_text: str, receipt: dict) -> dict:
    """Lint user-visible output against verifier/render receipt.

    This is deliberately conservative. It catches common public-render leaks:
    missing/wrong move emoji, 252 EV notation, final output with failed gates,
    and KO/survival claims without a damage receipt.
    """
    failures = []
    warnings = []
    render = receipt.get("public_render") or build_public_render(receipt) if receipt.get("mode") == "full_team_verification" else receipt.get("public_render", {})
    if receipt.get("mode") == "full_team_verification" and not receipt.get("team_ok"):
        if re.search(r"Team at a glance|✅\s*Team|ทีมหลัก|final team", answer_text, re.I):
            failures.append({"code": "FAIL_PUBLIC_RENDER_FINAL_WITH_FAILED_TEAM_GATE", "detail": "answer looks like a final team but team_ok is false"})
    # Move display checks.
    move_receipts = []
    if receipt.get("mode") == "full_team_verification":
        move_receipts = [m for r in receipt.get("sets", []) for m in r.get("moves", []) if m.get("status") == "pass"]
    for m in move_receipts:
        name = m.get("move_name", "")
        emoji = m.get("emoji", "")
        display = m.get("display") or (f"{emoji} {name}" if emoji else name)
        if not name:
            continue
        # If the move name appears anywhere in final output, require exact display to appear.
        if re.search(r"(?<![A-Za-z])" + re.escape(name) + r"(?![A-Za-z])", answer_text):
            if display not in answer_text:
                failures.append({"code": "FAIL_PUBLIC_RENDER_MISSING_MOVE_EMOJI", "move": name, "expected_display": display})
            # Wrong emoji immediately before move name.
            wrong = re.findall(r"([" + re.escape(_PUBLIC_TYPE_EMOJIS) + r"](?:️)?)\s+" + re.escape(name), answer_text)
            for e in wrong:
                if emoji and e != emoji:
                    failures.append({"code": "FAIL_PUBLIC_RENDER_WRONG_MOVE_EMOJI", "move": name, "expected_emoji": emoji, "seen_emoji": e})
    # Type display checks: public type labels in team/card output must include verifier emoji.
    if receipt.get("mode") == "full_team_verification":
        render_rows = (render or {}).get("team_table_rows", []) or []
        for row in render_rows:
            expected_type = str(row.get("type", ""))
            if not expected_type:
                continue
            # Bare pairs such as Grass/Ghost or Grass / Ghost are not allowed when this slot is rendered.
            type_names = [part.strip().split(" ", 1)[-1] for part in expected_type.split("/") if part.strip()]
            if type_names and row.get("pokemon") and str(row.get("pokemon")) in answer_text:
                bare_join = r"\s*/\s*".join(re.escape(x) for x in type_names)
                if re.search(bare_join, answer_text, re.I) and expected_type not in answer_text:
                    failures.append({"code": "FAIL_PUBLIC_RENDER_MISSING_TYPE_EMOJI", "pokemon": row.get("pokemon"), "expected_type_display": expected_type})

    if re.search(r"\bEVs?\b|\b252\b", answer_text, re.I):
        failures.append({"code": "FAIL_PUBLIC_RENDER_EV_STYLE_252", "detail": "Pokémon Champions spreads must be 0-32 per stat and total 66/66"})
    if re.search(r"สุ่ม|randomly|guess", answer_text, re.I) and re.search(r"Stat plan|Spread|Investment|สเปรด", answer_text, re.I):
        warnings.append({"code": "WARN_SPREAD_DESCRIBED_AS_GUESS", "detail": "Final spread should be meta baseline or benchmark override, not a bare guess."})
    raw_spread_pattern = r"(?<!\d)(?:\d{1,2}\s*/\s*){5}\d{1,2}(?!\d)"
    if re.search(raw_spread_pattern, answer_text) and not re.search(r"HP\s*/\s*Atk\s*/\s*Def\s*/\s*SpA\s*/\s*SpD\s*/\s*Spe|HP\s*\d+\s*/\s*Atk\s*\d+", answer_text, re.I):
        failures.append({"code": "FAIL_PUBLIC_RENDER_RAW_SPREAD_UNLABELED", "detail": "Bare spread strings like 32/0/32/0/2/0 are not public-safe. Label stats as HP 32 / Atk 0 / Def 32 / SpA 0 / SpD 2 / Spe 0."})
    if re.search(r"\|[^\n]*Item[^\n]*\|[^\n]*Move", answer_text, re.I) and re.search(r"\b(?:Jolly|Adamant|Modest|Timid|Impish|Careful|Calm|Quiet)\s*<br>|\b(?:Jolly|Adamant|Modest|Timid|Impish|Careful|Calm|Quiet)\s*\n\s*\d+\s*/", answer_text, re.I):
        warnings.append({"code": "WARN_PUBLIC_TABLE_TOO_DENSE", "detail": "Nature/spread should be in Detailed sets, not crammed into item/move overview columns."})
    if re.search(r"[┌┐└┘╭╮╰╯]", answer_text):
        failures.append({"code": "FAIL_ASCII_BOX_CARD_LAYOUT", "detail": "Manual ASCII/box-border card layout is disallowed. Claude card must use canonical HTML via widget/artifact; non-Claude card must be inline Markdown ASCII without box borders."})
    if re.search(r"<div[^>]+style=|<pre[^>]+style=|display\s*:\s*flex\s*;", answer_text, re.I):
        failures.append({"code": "FAIL_RAW_HTML_CARD_PRINTED_IN_TEXT", "detail": "Claude HTML cards are widget/artifact payloads. Do not paste raw HTML in chat text; use the platform display tool or inline ASCII fallback."})
    # v29.21: item-reason lint for Armor Tail / Prankster interaction.
    if re.search(r"Mental\s+Herb", answer_text, re.I) and re.search(r"Prankster|Whimsicott", answer_text, re.I) and re.search(r"Taunt|Encore", answer_text, re.I) and re.search(r"Armor\s+Tail|Farigiraf", answer_text, re.I):
        warnings.append({
            "code": "WARN_MENTAL_HERB_REASON_INVALID_VS_PRANKSTER_ARMOR_TAIL",
            "detail": "If Armor Tail is active, do not present Mental Herb as the main answer to Prankster Taunt/Encore; use verify.py interaction/threatfit and explain non-priority/bypass cases separately."
        })

    if re.search(r"\b(OHKO|2HKO|KO chance|guaranteed|survives?|damage rolls?|live\b|tank|avoid\s+KO|\d+(?:\.\d+)?%\s*-\s*\d+(?:\.\d+)?%)\b|การันตี|รอด(?:\s*1)?|ทน|รับ(?:ท่า|ดาเมจ)?|ไม่ตาย|ช่วย(?:ให้)?รอด|ตายทุก|ดาเมจ\s*\d", answer_text, re.I):
        has_damage = receipt.get("mode") in {"damage_verification", "stateful_sequence_verification"} or bool(receipt.get("damage_receipts"))
        if receipt.get("mode") == "full_team_verification":
            has_damage = bool(receipt.get("damage_receipts"))
        if not has_damage:
            failures.append({"code": "FAIL_SURVIVAL_CLAIM_WITHOUT_DAMAGE_RECEIPT", "detail": "Concrete KO/survival/tanking/damage claims require verify.py damage/sequence receipt before final output."})
    if re.search(r"(?i)(Drizzle|ฝน|rain|Weather\s+Ball|Hurricane|Sand\s+Rush|Swift\s+Swim|Chlorophyll|Slush\s+Rush).*(boost|accuracy|power|แรง|แม่น|ตั้ง|เปลี่ยน|คูณ|x2|×2|เร็ว)", answer_text):
        verified = _collect_verified_entities_from_receipt(receipt or {})
        has_mech = bool(verified.get("interaction") or verified.get("boardscan") or verified.get("mechanic"))
        if not has_mech:
            failures.append({"code": "FAIL_WEATHER_MECHANIC_REASON_WITHOUT_RECEIPT", "detail": "Weather/field/move interaction claims require local mechanic, interaction, boardscan, or typepassive receipt."})
    speed_mode_claim = re.search(r"Tailwind|Trick\s*Room|speed\s*mode|dual\s*mode|เปิด\s*Tailwind|เปิด\s*Trick\s*Room|เจอทีม(?:เร็ว|ช้า|ถึก)|ทีม(?:เร็ว|ช้า|ถึก)|ตัวใหญ่", answer_text, re.I)
    if speed_mode_claim:
        sp_gate = ((receipt or {}).get("team_gates", {}) or {}).get("speed_plan", {})
        has_speedplan = sp_gate.get("entity") == "speed_plan_receipt" and sp_gate.get("status") in {"pass", "pass_with_warnings"}
        if not has_speedplan:
            failures.append({"code": "FAIL_SPEED_MODE_CLAIM_WITHOUT_SPEEDPLAN_RECEIPT", "detail": "Tailwind/Trick Room/speed-mode advice requires verify.py speedplan receipt; do not recommend from vague fast/slow/bulky labels."})
        if re.search(r"เจอทีม(?:ช้า|ถึก|ตัวใหญ่).*Trick\s*Room|Trick\s*Room.*เจอทีม(?:ช้า|ถึก|ตัวใหญ่)|slow.*Trick\s*Room|bulky.*Trick\s*Room", answer_text, re.I) and not has_speedplan:
            failures.append({"code": "FAIL_TRICK_ROOM_RECOMMENDATION_WITHOUT_BENEFICIARY_CHECK", "detail": "Do not say to use Trick Room into slow/bulky teams unless speedplan proves it benefits your active attackers more than the opponent."})
    lead_claim = re.search(r"Lead|lead|เปิดด้วย|นำด้วย|เทิร์น\s*1|Turn\s*1|T1:", answer_text, re.I)
    if lead_claim:
        lp_gate = ((receipt or {}).get("team_gates", {}) or {}).get("lead_plan", {})
        has_leadplan = lp_gate.get("entity") == "lead_plan_receipt" and lp_gate.get("status") in {"pass", "pass_with_warnings"}
        if not has_leadplan and receipt.get("mode") == "full_team_verification":
            failures.append({"code": "FAIL_LEAD_PLAN_WITHOUT_TURN_SIMULATION", "detail": "Lead advice requires verify.py leadplan receipt with short Turn 1-2 simulation and risks."})
    type_failures, type_warnings = _type_claim_guard(answer_text, receipt)
    failures.extend(type_failures)
    warnings.extend(type_warnings)
    entity_failures, entity_warnings = _public_entity_guard(answer_text, receipt)
    failures.extend(entity_failures)
    warnings.extend(entity_warnings)
    tp_failures, tp_warnings = _typepassive_claim_guard(answer_text, receipt)
    failures.extend(tp_failures)
    warnings.extend(tp_warnings)
    mech_failures, mech_warnings = _mechanic_claim_guard(answer_text, receipt)
    failures.extend(mech_failures)
    warnings.extend(mech_warnings)
    stat_failures, stat_warnings = _base_stat_claim_guard(answer_text, receipt)
    failures.extend(stat_failures)
    warnings.extend(stat_warnings)
    adj_failures, adj_warnings = _semantic_stat_adjective_guard(answer_text, receipt)
    failures.extend(adj_failures)
    warnings.extend(adj_warnings)
    mech2_failures, mech2_warnings = _mechanic_overinterpret_guard(answer_text, receipt)
    failures.extend(mech2_failures)
    warnings.extend(mech2_warnings)
    sem_failures, sem_warnings = _semantic_audit_presence_guard(answer_text, receipt)
    failures.extend(sem_failures)
    warnings.extend(sem_warnings)
    status = "pass" if not failures else "fail"
    return {
        "mode": "public_output_lint",
        "status": status,
        "failures": failures,
        "warnings": warnings,
        "typechart_receipts_found": [r.get("display") for r in _collect_typechart_receipts(receipt)],
        "rule": "Final public output must match verifier/render fields. No local receipt = no named entity. No meta/player baseline receipt = no actionable final recommendation. No typechart receipt = no type claim. No typepassive receipt = no type passive/status/weather/hazard claim. No boardscan/interaction/mechanic/counterroute receipt = no mechanic, ally-damage, or hard-counter claim. Run selfaudit/lint before final. lint pass is not semantic verification; item/risk/stat/mechanic prose also needs threataudit, stat, mechanic, and itemthreatfit receipts.",
    }



def verify_final_self_audit(answer_text: str, receipt: dict) -> dict:
    """Bounded draft re-read gate.

    It does not "think again" freely. It extracts public claims via lint-output,
    reports unsupported claims, and requires one repair pass followed by re-lint.
    """
    lint = lint_public_output(answer_text, receipt)
    actions = []
    for f in lint.get("failures", []):
        code = f.get("code", "")
        if "WITHOUT" in code or "UNVERIFIED" in code:
            actions.append({"code": code, "action": "remove the unsupported claim or run the exact verifier command and re-lint"})
        elif "COUNTER" in code:
            actions.append({"code": code, "action": "downgrade hard-counter wording or add counterroute receipt"})
        else:
            actions.append({"code": code, "action": "repair the line and run lint-output again"})
    return {
        "mode": "final_self_audit",
        "status": "pass" if lint.get("status") == "pass" else "fail",
        "lint": lint,
        "repair_actions": actions,
        "rule": "Draft answer -> extract public claims -> lint/verify -> repair once -> re-lint -> final. Do not add new claims during repair without receipts.",
    }

def verify_team(team_payload) -> dict:
    """Verify a full team and enforce team-level legality gates.

    Hard gates implemented here:
    - each individual set must pass (Pokémon / ability / item / all moves)
    - full final-team payload should contain exactly 6 sets
    - Item Clause / Unique Item Gate defaults to ON

    Soft warnings implemented here:
    - Choice item + Protect
    - Tailwind and Trick Room on the same team without an explicit plan
    - Trick Room present, because setup turn must respect priority -7
    - Prankster support present, because priority claims must use ability + Status move receipts
    - Other priority moves present, because priority bracket beats Speed
    - Earthquake present, because ally damage must be board-checked in Doubles
    """
    team_list, item_clause, spread_required = _extract_team_list(team_payload)
    out = {
        "mode": "full_team_verification",
        "input_count": len(team_list) if isinstance(team_list, list) else 0,
        "item_clause": item_clause,
        "spread_required": spread_required,
        "sets": [],
        "team_gates": {},
        "warnings": [],
        "input_payload": team_payload,
    }

    if not isinstance(team_list, list) or not team_list:
        out["team_ok"] = False
        out["reason"] = "team payload must be a list of set objects or an object with a 'team' list"
        return out

    for slot, set_object in enumerate(team_list, start=1):
        receipt = verify_set(set_object)
        receipt["slot"] = slot
        out["sets"].append(receipt)

    individual_ok = all(r.get("set_ok") is True for r in out["sets"])
    out["team_gates"]["individual_sets"] = {
        "status": "pass" if individual_ok else "fail",
        "passed": sum(1 for r in out["sets"] if r.get("set_ok") is True),
        "total": len(out["sets"]),
    }

    full_team_ok = len(out["sets"]) == 6
    out["team_gates"]["team_size"] = {
        "status": "pass" if full_team_ok else "fail",
        "expected": 6,
        "actual": len(out["sets"]),
    }

    active_pass_count = sum(1 for r in out["sets"] if r.get("active_form", {}).get("status") == "pass")
    active_failures = []
    active_changed = []
    for r in out["sets"]:
        af = r.get("active_form", {})
        if af.get("status") != "pass":
            active_failures.append({
                "slot": r.get("slot"),
                "pokemon": r.get("pokemon_gate", {}).get("name", r.get("input", {}).get("pokemon", "unknown")),
                "code": af.get("code", "FAIL_ACTIVE_FORM_MISSING"),
                "reason": af.get("reason", "active-form resolution failed"),
            })
        elif af.get("active_changed"):
            active_changed.append({
                "slot": r.get("slot"),
                "display_name": af.get("display_name"),
                "team_form_id": af.get("team_form_id"),
                "active_form_id": af.get("active_form_id"),
                "form_trigger": af.get("form_trigger"),
                "stat_source": af.get("stat_source"),
            })
    out["team_gates"]["active_form_resolution"] = {
        "status": "pass" if active_pass_count == len(out["sets"]) else "fail",
        "passed": active_pass_count,
        "total": len(out["sets"]),
        "active_changed": active_changed,
        "failures": active_failures,
        "rule": "team_form selects the roster slot; active_form is the battle stat/type/ability source.",
    }

    spread_pass_count = sum(1 for r in out["sets"] if r.get("spread", {}).get("status") == "pass")
    spread_failures = []
    for r in out["sets"]:
        sp = r.get("spread", {})
        if sp.get("status") != "pass":
            spread_failures.append({
                "slot": r.get("slot"),
                "pokemon": r.get("pokemon_gate", {}).get("name", r.get("input", {}).get("pokemon", "unknown")),
                "status": sp.get("status", "fail"),
                "reason": sp.get("reason", "missing or invalid spread"),
                "spread": sp.get("spread"),
            })
    spread_gate_status = "pass" if (not spread_required or spread_pass_count == len(out["sets"])) else "fail"
    out["team_gates"]["stat_spreads_0_32_66"] = {
        "status": spread_gate_status,
        "spread_required": spread_required,
        "passed": spread_pass_count,
        "total": len(out["sets"]),
        "failures": spread_failures,
    }

    stat_pass_count = sum(1 for r in out["sets"] if r.get("displayed_stats", {}).get("status") == "pass")
    stat_failures = []
    for r in out["sets"]:
        st = r.get("displayed_stats", {})
        if st.get("status") != "pass":
            stat_failures.append({
                "slot": r.get("slot"),
                "pokemon": r.get("pokemon_gate", {}).get("name", r.get("input", {}).get("pokemon", "unknown")),
                "status": st.get("status", "fail"),
                "reason": st.get("reason", "missing or invalid stat receipt"),
            })
    stat_gate_status = "pass" if (not spread_required or stat_pass_count == len(out["sets"])) else "fail"
    out["team_gates"]["displayed_stats"] = {
        "status": stat_gate_status,
        "stat_required": spread_required,
        "passed": stat_pass_count,
        "total": len(out["sets"]),
        "failures": stat_failures,
        "rule": "No stat receipt = no public displayed stat number. Nature + 0-32/66 spread are required.",
    }

    # Unique Item / Item Clause gate.
    item_users = {}
    for r in out["sets"]:
        item = r.get("item", {})
        if item.get("status") == "pass":
            item_id = item.get("id", normalize_id(item.get("query", "")))
            item_name = item.get("name", item_id)
        else:
            item_id = normalize_id(r.get("input", {}).get("item", ""))
            item_name = r.get("input", {}).get("item", item_id)
        item_users.setdefault(item_id, {"name": item_name, "users": []})
        item_users[item_id]["users"].append(r.get("pokemon_gate", {}).get("name", r.get("input", {}).get("pokemon", f"slot{r.get('slot')}")))

    duplicates = {
        item_id: info for item_id, info in item_users.items()
        if item_id and len(info["users"]) > 1
    }
    unique_status = "pass"
    if item_clause and duplicates:
        unique_status = "fail"
    out["team_gates"]["unique_items_item_clause"] = {
        "status": unique_status,
        "item_clause": item_clause,
        "duplicates": duplicates,
    }

    # Soft compatibility warnings and priority/mechanic receipts.
    all_move_ids = set()
    priority_receipts = []
    for r in out["sets"]:
        pokemon_name = r.get("active_form", {}).get("active_form", {}).get("name", r.get("pokemon_gate", {}).get("name", r.get("input", {}).get("pokemon", "unknown")))
        ability_name = r.get("ability", {}).get("ability_name", r.get("input", {}).get("battle_ability", r.get("input", {}).get("ability", "")))
        ability_id = normalize_id(ability_name)
        item = r.get("item", {})
        item_id = item.get("id", normalize_id(r.get("input", {}).get("item", "")))
        move_receipts = r.get("moves", [])
        move_ids = {m.get("move_id", normalize_id(m.get("move_query", ""))) for m in move_receipts}
        all_move_ids.update(move_ids)
        for m in move_receipts:
            mid = normalize_id(m.get("move_id", m.get("move_query", "")))
            cat = str(m.get("category", "")).strip().lower()
            is_priority_exception = mid in PRIORITY_MOVE_RULES and int(PRIORITY_MOVE_RULES[mid].get("priority", 0)) != 0
            is_prankster_status = ability_id == "prankster" and cat == "status"
            if is_priority_exception or is_prankster_status:
                pr = verify_priority_on_pokemon(pokemon_name, m.get("move_name", m.get("move_query", mid)), ability_name)
                priority_receipts.append(pr)
        if item_id in CHOICE_ITEM_IDS and "protect" in move_ids:
            out["warnings"].append({
                "code": "WARN_CHOICE_ITEM_WITH_PROTECT",
                "pokemon": pokemon_name,
                "item": item.get("name", item_id),
                "detail": "Choice item + Protect is usually a bad 2v2 compatibility pattern; replace Protect or replace the item unless a specific verified plan justifies it.",
            })
        if "earthquake" in move_ids:
            out["warnings"].append({
                "code": "WARN_EARTHQUAKE_ALLY_DAMAGE",
                "pokemon": pokemon_name,
                "detail": "Earthquake is a spread move that can hit the ally; final lead/turn plans must verify ally immunity, Protect, or acceptable sacrifice.",
            })

    if "tailwind" in all_move_ids and "trickroom" in all_move_ids:
        out["warnings"].append({
            "code": "WARN_TAILWIND_TRICK_ROOM_CONFLICT",
            "detail": "Tailwind and Trick Room can conflict. Output must state distinct game plans and avoid using both as one combined plan.",
        })

    if "trickroom" in all_move_ids:
        out["warnings"].append({
            "code": "WARN_TRICK_ROOM_PRIORITY_MINUS_7",
            "mechanic_receipt": verify_mechanic("Trick Room"),
            "detail": "Trick Room is priority -7. Do not claim a fast Trick Room setter moves before normal-priority attacks; final lead plan must include Fake Out, Protect, redirection, bulk, or another verified survival/safety plan for the setup turn.",
        })

    if any(pr.get("prankster_applied") for pr in priority_receipts):
        out["warnings"].append({
            "code": "INFO_PRANKSTER_STATUS_PRIORITY_PLUS_1",
            "mechanic_receipt": verify_mechanic("Prankster"),
            "detail": "Prankster gives +1 only to verified eligible Status support moves. Do not apply it to attacks, and board/target blocks still need checking.",
        })

    if priority_receipts:
        out["team_gates"]["priority_mechanics"] = {
            "status": "pass",
            "receipt_count": len(priority_receipts),
            "receipts": priority_receipts,
            "rule": "Priority bracket is checked before Speed; Speed only orders Pokémon inside the same priority bracket.",
        }
    else:
        out["team_gates"]["priority_mechanics"] = {
            "status": "pass",
            "receipt_count": 0,
            "rule": "No priority exception or verified Prankster Status move detected in the final team payload.",
        }

    teamfit_receipt = evaluate_team_fit(out)
    out["team_gates"]["team_fit"] = teamfit_receipt
    item_prov_failures = [f for f in teamfit_receipt.get("failures", []) if f.get("code") == "FAIL_ITEM_SOURCE_UNLABELED"]
    spread_prov_failures = [f for f in teamfit_receipt.get("failures", []) if f.get("code") == "FAIL_SPREAD_SOURCE_UNLABELED"]
    out["team_gates"]["item_provenance"] = {"status": "fail" if item_prov_failures else "pass", "failures": item_prov_failures, "allowed_labels": sorted(PROVENANCE_LABELS), "rule": "Every final item must be provenance-labeled."}
    out["team_gates"]["spread_provenance"] = {"status": "fail" if spread_prov_failures else "pass", "failures": spread_prov_failures, "allowed_labels": sorted(PROVENANCE_LABELS), "rule": "Every final spread must be provenance-labeled and team-fit justified."}
    for warn in teamfit_receipt.get("warnings", []):
        if warn not in out["warnings"]:
            out["warnings"].append(warn)

    # v29.24 metaspreaddiffgate / benchmarkoverridegate.
    explicit_meta_spreads = None
    if isinstance(team_payload, dict):
        explicit_meta_spreads = team_payload.get("meta_spreads") or team_payload.get("meta_spread_baselines")
    spreadfit_receipt = evaluate_spread_fit(out, explicit_meta_spreads)
    out["team_gates"]["spread_fit"] = spreadfit_receipt
    for warn in spreadfit_receipt.get("warnings", []):
        if warn not in out["warnings"]:
            out["warnings"].append(warn)

    # v29.35 itemspreadcoherencegate / reasonreceiptgate.
    itemspread_receipt = evaluate_item_spread_coherence(out)
    out["team_gates"]["item_spread_coherence"] = itemspread_receipt
    for warn in itemspread_receipt.get("warnings", []):
        if warn not in out["warnings"]:
            out["warnings"].append(warn)

    # v29.38 decisiontrace / speedmode / lead simulation gates.
    speedplan_receipt = evaluate_speed_plan(out)
    out["team_gates"]["speed_plan"] = speedplan_receipt
    for warn in speedplan_receipt.get("warnings", []):
        if warn not in out["warnings"]:
            out["warnings"].append(warn)
    leadplan_receipt = evaluate_lead_plan(out)
    out["team_gates"]["lead_plan"] = leadplan_receipt
    for warn in leadplan_receipt.get("warnings", []):
        if warn not in out["warnings"]:
            out["warnings"].append(warn)

    # v29.39 semanticthreataudit / statclaim / itemthreatprofile gates.
    threataudit_receipt = evaluate_threat_audit(out)
    out["team_gates"]["threat_audit"] = threataudit_receipt
    for warn in threataudit_receipt.get("warnings", []):
        if warn not in out["warnings"]:
            out["warnings"].append(warn)
    itemthreatfit_receipt = evaluate_item_threat_fit(out)
    out["team_gates"]["item_threat_fit"] = itemthreatfit_receipt
    for warn in itemthreatfit_receipt.get("warnings", []):
        if warn not in out["warnings"]:
            out["warnings"].append(warn)

    # v29.21 mechanicinteractiongate / metathreatfitgate.
    explicit_threats = None
    if isinstance(team_payload, dict):
        explicit_threats = team_payload.get("meta_threats") or team_payload.get("threats")
    threatfit_receipt = evaluate_threat_fit(out, explicit_threats)
    out["team_gates"]["meta_threat_fit"] = threatfit_receipt
    out["team_gates"]["mechanic_interactions"] = {
        "status": "pass",
        "receipts": [],
        "rule": "Named mechanic counter claims require verify.py interaction receipts; threatfit supplies team-level interaction summaries.",
    }
    # Materialize interaction receipts for common threatfit rows so render has concrete relationship summaries.
    for tr in threatfit_receipt.get("threats_checked", []):
        norm = normalize_id(str(tr.get("threat", "")) + " " + " ".join(tr.get("examples", []) if isinstance(tr.get("examples"), list) else []))
        armor_users = _team_has_ability(out, "armortail")
        if armor_users and ("prankster" in norm or "taunt" in norm or "encore" in norm):
            # Use Whimsicott examples if locally available; if not, receipt will fail closed.
            for mv in ["Taunt", "Encore"]:
                rec = verify_interaction({"actor": {"pokemon": "Whimsicott", "ability": "Prankster", "move": mv}, "target": {"pokemon": armor_users[0]["pokemon"], "ability": "Armor Tail"}, "context": {"format": "2v2", "source": "auto-threatfit"}})
                out["team_gates"]["mechanic_interactions"]["receipts"].append(rec)
        if armor_users and ("fakeout" in norm):
            # Incineroar is common, but if local interaction fails it stays as a receipt failure rather than a claim.
            rec = verify_interaction({"actor": {"pokemon": "Incineroar", "ability": "Intimidate", "move": "Fake Out"}, "target": {"pokemon": armor_users[0]["pokemon"], "ability": "Armor Tail"}, "context": {"format": "2v2", "source": "auto-threatfit"}})
            out["team_gates"]["mechanic_interactions"]["receipts"].append(rec)
    if any(r.get("status") == "fail" for r in out["team_gates"]["mechanic_interactions"].get("receipts", [])):
        out["team_gates"]["mechanic_interactions"]["status"] = "fail"
    elif out["team_gates"]["mechanic_interactions"].get("receipts"):
        out["team_gates"]["mechanic_interactions"]["status"] = "pass"
    for warn in threatfit_receipt.get("warnings", []):
        if warn not in out["warnings"]:
            out["warnings"].append(warn)

    spread_ok = out["team_gates"]["stat_spreads_0_32_66"]["status"] == "pass"
    displayed_stats_ok = out["team_gates"]["displayed_stats"]["status"] == "pass"
    active_ok = out["team_gates"]["active_form_resolution"]["status"] == "pass"
    provenance_ok = out["team_gates"]["item_provenance"]["status"] == "pass" and out["team_gates"]["spread_provenance"]["status"] == "pass"
    teamfit_ok = teamfit_receipt.get("status") in {"pass", "pass_with_warnings"}
    threatfit_ok = threatfit_receipt.get("status") in {"pass", "pass_with_warnings"}
    interaction_ok = out["team_gates"].get("mechanic_interactions", {}).get("status") != "fail"
    spreadfit_ok = out["team_gates"].get("spread_fit", {}).get("status") in {"pass", "pass_with_warnings"}
    itemspread_ok = out["team_gates"].get("item_spread_coherence", {}).get("status") in {"pass", "pass_with_warnings"}
    threataudit_ok = out["team_gates"].get("threat_audit", {}).get("status") in {"pass", "pass_with_warnings"}
    itemthreatfit_ok = out["team_gates"].get("item_threat_fit", {}).get("status") in {"pass", "pass_with_warnings"}
    team_ok = individual_ok and full_team_ok and unique_status == "pass" and spread_ok and displayed_stats_ok and active_ok and provenance_ok and teamfit_ok and spreadfit_ok and itemspread_ok and threataudit_ok and itemthreatfit_ok and threatfit_ok and interaction_ok
    out["team_ok"] = team_ok
    out["team_gates"]["team_compatibility"] = {
        "status": "pass" if team_ok and not out["warnings"] else ("pass_with_warnings" if team_ok else "fail"),
        "warning_count": len(out["warnings"]),
        "hard_fail_count": 0 if team_ok else 1,
    }
    out["public_render"] = build_public_render(out)
    move_emoji_row = next((rr for rr in out["public_render"].get("receipt_rows", []) if rr.get("gate") == "Move emoji rendering"), {})
    out["team_gates"]["move_emoji_rendering"] = {
        "status": "pass" if str(move_emoji_row.get("result", "")).endswith("PASS") else "fail",
        "source": "move.display from 05-07 receipt",
        "rule": "Every public move display must use the verified move row type emoji.",
    }
    out["team_gates"]["public_render"] = {
        "status": out["public_render"].get("status", "fail"),
        "source": "verify.py render",
        "rule": "Public output must copy verifier-generated display fields; do not reconstruct manually.",
    }
    return out



def _main():
    if len(sys.argv) < 2:
        print(json.dumps({"status": "fail", "reason": "no command given"}))
        sys.exit(1)

    cmd = sys.argv[1]
    try:
        if cmd == "pokemon":
            result = verify_pokemon(sys.argv[2])
        elif cmd == "strict_mb":
            result = verify_strict_mb(sys.argv[2])
        elif cmd == "ascii-assets":
            result = ascii_assets_status()
        elif cmd == "image-assets":
            result = image_assets_status()
        elif cmd == "item":
            result = verify_item(sys.argv[2])
        elif cmd == "ability":
            result = verify_ability_on_pokemon(sys.argv[2], sys.argv[3])
        elif cmd == "move":
            result = verify_move_on_pokemon(sys.argv[2], sys.argv[3])
        elif cmd == "set":
            with open(sys.argv[2], "r", encoding="utf-8") as f:
                set_object = json.load(f)
            result = verify_set(set_object)
        elif cmd == "team":
            with open(sys.argv[2], "r", encoding="utf-8") as f:
                team_object = json.load(f)
            result = verify_team(team_object)
        elif cmd == "teamfit":
            with open(sys.argv[2], "r", encoding="utf-8") as f:
                team_object = json.load(f)
            result = verify_teamfit(team_object)
        elif cmd == "itemspread":
            with open(sys.argv[2], "r", encoding="utf-8") as f:
                team_object = json.load(f)
            result = verify_itemspread(team_object)
        elif cmd == "speedplan":
            with open(sys.argv[2], "r", encoding="utf-8") as f:
                team_object = json.load(f)
            result = verify_speedplan(team_object)
        elif cmd == "leadplan":
            with open(sys.argv[2], "r", encoding="utf-8") as f:
                team_object = json.load(f)
            result = verify_leadplan(team_object)
        elif cmd == "threataudit":
            with open(sys.argv[2], "r", encoding="utf-8") as f:
                team_object = json.load(f)
            result = verify_threataudit(team_object)
        elif cmd == "itemthreatfit":
            with open(sys.argv[2], "r", encoding="utf-8") as f:
                team_object = json.load(f)
            result = verify_itemthreatfit(team_object)
        elif cmd == "interaction":
            scenario = _load_json_arg(" ".join(sys.argv[2:]))
            result = verify_interaction(scenario)
        elif cmd == "boardscan":
            scenario = _load_json_arg(" ".join(sys.argv[2:]))
            result = verify_boardscan(scenario)
        elif cmd == "counterroute":
            scenario = _load_json_arg(" ".join(sys.argv[2:]))
            result = verify_counterroute(scenario)
        elif cmd == "selfaudit":
            with open(sys.argv[2], "r", encoding="utf-8") as f:
                answer_text = f.read()
            with open(sys.argv[3], "r", encoding="utf-8") as f:
                receipt_object = json.load(f)
            result = verify_final_self_audit(answer_text, receipt_object)
        elif cmd == "mechanic-regression-tests":
            cases = [
                {"name": "Intimidate vs Contrary", "scenario": {"actor": {"ability": "Intimidate"}, "target": {"ability": "Contrary"}}, "expect": "pass"},
                {"name": "Thunder Wave vs Contrary", "scenario": {"actor": {"move": "Thunder Wave"}, "target": {"ability": "Contrary"}}, "expect": "pass"},
                {"name": "Gale Wings Brave Bird no hp receipt", "scenario": {"actor": {"ability": "Gale Wings", "move": "Brave Bird"}}, "expect": "pass_with_warnings"},
                {"name": "Pixilate Hyper Voice", "scenario": {"actor": {"ability": "Pixilate", "move": "Hyper Voice"}}, "expect": "pass"},
            ]
            receipts = []
            failures = []
            for c in cases:
                rec = verify_interaction(c["scenario"])
                receipts.append({"name": c["name"], "receipt": rec})
                if rec.get("status") != c["expect"]:
                    failures.append({"case": c["name"], "expected": c["expect"], "actual": rec.get("status"), "receipt": rec})
            result = {"mode": "mechanic_regression_tests", "status": "pass" if not failures else "fail", "receipts": receipts, "failures": failures}
        elif cmd == "threatfit":
            with open(sys.argv[2], "r", encoding="utf-8") as f:
                team_object = json.load(f)
            threats = None
            if len(sys.argv) > 3:
                threats = _load_json_arg(sys.argv[3])
            result = verify_threatfit(team_object, threats)
        elif cmd == "spreadfit":
            with open(sys.argv[2], "r", encoding="utf-8") as f:
                team_object = json.load(f)
            meta_spreads = None
            if len(sys.argv) > 3:
                meta_spreads = _load_json_arg(sys.argv[3])
            result = verify_spreadfit(team_object, meta_spreads)
        elif cmd == "render":
            with open(sys.argv[2], "r", encoding="utf-8") as f:
                team_object = json.load(f)
            style = "compact"
            platform = "portable"
            if "--style" in sys.argv:
                i = sys.argv.index("--style")
                if i + 1 < len(sys.argv):
                    style = sys.argv[i + 1]
            if "--platform" in sys.argv:
                i = sys.argv.index("--platform")
                if i + 1 < len(sys.argv):
                    platform = sys.argv[i + 1]
            print(render_team_markdown(team_object, style=style, platform=platform), end="")
            return
        elif cmd == "lint-output":
            with open(sys.argv[2], "r", encoding="utf-8") as f:
                answer_text = f.read()
            with open(sys.argv[3], "r", encoding="utf-8") as f:
                receipt_object = json.load(f)
            result = lint_public_output(answer_text, receipt_object)
        elif cmd == "spread":
            raw = sys.argv[2]
            try:
                spread_object = json.loads(raw)
            except Exception:
                spread_object = raw
            result = verify_spread(spread_object)
        elif cmd == "active-form":
            raw = " ".join(sys.argv[2:])
            try:
                obj = _load_json_arg(raw)
            except Exception:
                obj = {"pokemon": raw}
            result = verify_active_form(obj)
        elif cmd == "stat":
            raw = sys.argv[4]
            try:
                spread_object = json.loads(raw)
            except Exception:
                spread_object = raw
            state_object = None
            if len(sys.argv) > 5:
                state_raw = " ".join(sys.argv[5:])
                try:
                    state_object = _load_json_arg(state_raw)
                except Exception:
                    try:
                        state_object = json.loads(state_raw)
                    except Exception:
                        state_object = {"active_form": state_raw}
            result = verify_stat(sys.argv[2], sys.argv[3], spread_object, state_object)
        elif cmd == "damage":
            scenario = _load_json_arg(sys.argv[2])
            result = verify_damage(scenario)
        elif cmd == "sequence":
            scenario = _load_json_arg(sys.argv[2])
            result = verify_sequence(scenario)
        elif cmd == "mechanic":
            result = verify_mechanic(" ".join(sys.argv[2:]))
        elif cmd == "priority":
            ability = " ".join(sys.argv[4:]) if len(sys.argv) > 4 else ""
            result = verify_priority_on_pokemon(sys.argv[2], sys.argv[3], ability)
        elif cmd == "typechart":
            result = verify_type_effectiveness(sys.argv[2], " ".join(sys.argv[3:]))
        elif cmd == "typepassive":
            scenario = _load_json_arg(" ".join(sys.argv[2:]))
            result = verify_typepassive(scenario)
        elif cmd == "typepassive-regression-tests":
            cases = [
                {"name": "Dark blocks opposing Prankster Taunt", "scenario": {"defender": {"types": ["Dark"]}, "incoming": {"move": "Taunt", "category": "Status", "source_ability": "Prankster", "side": "opponent"}}, "expect": "pass"},
                {"name": "Ground blocks Thunder Wave", "scenario": {"defender": {"types": ["Ground"]}, "incoming": {"move": "Thunder Wave"}}, "expect": "pass"},
                {"name": "Rock in Sandstorm", "scenario": {"defender": {"types": ["Rock"]}, "incoming": {"weather": "Sandstorm"}}, "expect": "pass"},
                {"name": "Ice in Snow", "scenario": {"defender": {"types": ["Ice"]}, "incoming": {"weather": "Snow"}}, "expect": "pass"},
                {"name": "Flying grounded hazard requires ungrounded", "scenario": {"defender": {"types": ["Flying"]}, "incoming": {"hazard": "Spikes"}, "context": {"grounded": True}}, "expect": "not_applicable"},
                {"name": "Flying ungrounded avoids Spikes", "scenario": {"defender": {"types": ["Flying"]}, "incoming": {"hazard": "Spikes"}, "context": {"grounded": False}}, "expect": "pass"},
                {"name": "Poison grounded clears Toxic Spikes", "scenario": {"defender": {"types": ["Poison"]}, "incoming": {"hazard": "Toxic Spikes"}, "context": {"grounded": True}}, "expect": "pass"},
                {"name": "Fire burn immunity", "scenario": {"defender": {"types": ["Fire"]}, "incoming": {"status": "burn"}}, "expect": "pass"},
                {"name": "Electric paralysis immunity", "scenario": {"defender": {"types": ["Electric"]}, "incoming": {"status": "paralysis"}}, "expect": "pass"},
                {"name": "Ghost trapping immunity", "scenario": {"defender": {"types": ["Ghost"]}, "incoming": {"effect": "cannot_escape"}}, "expect": "pass"},
            ]
            receipts = []
            failures = []
            for c in cases:
                rec = verify_typepassive(c["scenario"])
                receipts.append({"name": c["name"], "receipt": rec})
                if rec.get("status") != c["expect"]:
                    failures.append({"case": c["name"], "expected": c["expect"], "actual": rec.get("status"), "receipt": rec})
            result = {"mode": "typepassive_regression_tests", "status": "pass" if not failures else "fail", "receipts": receipts, "failures": failures}
        elif cmd == "type-regression-tests":
            cases = [
                ("Ghost", "Dark", 0.5, "resisted"),
                ("Ghost", "Normal", 0.0, "immune"),
                ("Ghost", "Dark/Normal", 0.0, "immune"),
                ("Fire", "Steel/Dragon", 1.0, "neutral"),
                ("Ground", "Flying", 0.0, "immune"),
            ]
            receipts = []
            failures = []
            for atk, defender, expected, label in cases:
                rec = verify_type_effectiveness(atk, defender)
                receipts.append(rec)
                if rec.get("status") != "pass" or float(rec.get("total_type_multiplier", -1)) != expected or rec.get("label") != label:
                    failures.append({"case": f"{atk} -> {defender}", "expected": expected, "expected_label": label, "receipt": rec})
            result = {"mode": "type_regression_tests", "status": "pass" if not failures else "fail", "receipts": receipts, "failures": failures}
        else:
            result = {"status": "fail", "reason": f"unknown command '{cmd}'"}
    except IndexError:
        result = {"status": "fail", "reason": "missing arguments for command"}

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
