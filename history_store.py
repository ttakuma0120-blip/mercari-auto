"""
生成した紹介文の履歴を JSONL で保存・読み込み（Webアプリ・CLI 共通）
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

# プロジェクト直下 data/listing_history.jsonl
HISTORY_FILE = Path(__file__).resolve().parent / "data" / "listing_history.jsonl"
MAX_ENTRIES = 500


def _ensure_dir() -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)


def append_listing_history(data: dict) -> str:
    """
    生成結果を履歴に追加する。
    data は enrich 済みの辞書（description_full などを含む）。
    戻り値: 履歴エントリの id
    """
    _ensure_dir()
    entry = {
        "id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "title": (data.get("title") or "").strip(),
        "description_full": (
            data.get("description_full") or data.get("description") or ""
        ).strip(),
        "category_suggestion": (data.get("category_suggestion") or "").strip(),
        "price_suggestion": (data.get("price_suggestion") or "").strip(),
        "keywords": data.get("keywords") or [],
        "points_keywords": (data.get("points_keywords") or "").strip(),
        "points_checkmarks": (data.get("points_checkmarks") or "").strip(),
        "styling_tips": (data.get("styling_tips") or "").strip(),
        "color": (data.get("color") or "").strip(),
        "material": (data.get("material") or "").strip(),
        "condition": (data.get("condition") or "").strip(),
        "size_block": (data.get("size_block") or "").strip(),
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    _trim_to_max()
    return entry["id"]


def _trim_to_max() -> None:
    """件数が MAX_ENTRIES を超えたら古いものから削除"""
    entries = _read_all_entries()
    if len(entries) <= MAX_ENTRIES:
        return
    entries.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    kept = entries[:MAX_ENTRIES]
    kept.sort(key=lambda x: x.get("created_at", ""))
    _rewrite_all(kept)


def _read_all_entries() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    out: list[dict] = []
    with open(HISTORY_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _rewrite_all(entries: list[dict]) -> None:
    _ensure_dir()
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def load_history(limit: int = 100) -> list[dict]:
    """新しい順に limit 件まで返す"""
    entries = _read_all_entries()
    entries.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return entries[:limit]


def delete_entry(entry_id: str) -> bool:
    """id に一致する1件を削除。成功したら True"""
    entries = _read_all_entries()
    new_entries = [e for e in entries if e.get("id") != entry_id]
    if len(new_entries) == len(entries):
        return False
    new_entries.sort(key=lambda x: x.get("created_at", ""))
    _rewrite_all(new_entries)
    return True


def clear_all_history() -> None:
    """履歴ファイルを空にする"""
    _ensure_dir()
    if HISTORY_FILE.exists():
        HISTORY_FILE.write_text("", encoding="utf-8")
