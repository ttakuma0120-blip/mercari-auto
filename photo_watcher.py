"""
写真フォルダを監視して、メルカリ出品を半自動化するツール。

使い方:
  images/inbox/<商品名など任意のフォルダ名>/ を作り、その中に写真を入れる
  → 写真の追加が一定時間止まると自動で処理される
      1. Geminiで商品紹介文を生成
      2. 履歴（data/listing_history.jsonl）に保存
      3. ブラウザでメルカリの出品フォームを自動入力（新しいタブが開く）
  → 「出品する」ボタンは押されないので、内容を確認して自分で押してください

終了するには Ctrl+C を押してください。
"""

import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

# Windowsのコンソールで絵文字等のUnicode出力エラーを防ぐ
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

from google import genai

from history_store import append_listing_history
from mercari_autofill import ensure_logged_in, fill_mercari_listing, launch_browser
from mercari_listing_generator import (
    enrich_with_full_description,
    generate_listing,
    load_env_file,
    load_images,
    parse_result,
    research_price,
)

BASE_DIR = Path(__file__).parent
INBOX_DIR = BASE_DIR / "images" / "inbox"
DONE_DIR = INBOX_DIR / "_done"
ERROR_DIR = INBOX_DIR / "_error"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

# 写真の追加が止まってから処理を始めるまでの待ち時間（秒）
DEBOUNCE_SECONDS = 8
# フォルダを見に行く間隔（秒）
POLL_INTERVAL_SECONDS = 5


def _is_item_folder(p: Path) -> bool:
    return p.is_dir() and p.name not in ("_done", "_error")


def _folder_images(folder: Path) -> list[str]:
    files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS]
    files.sort(key=lambda f: f.name)
    return [str(f) for f in files]


def _folder_is_settled(folder: Path) -> bool:
    files = [f for f in folder.iterdir() if f.is_file()]
    if not files:
        return False
    newest = max(f.stat().st_mtime for f in files)
    return (time.time() - newest) >= DEBOUNCE_SECONDS


def _move_folder(folder: Path, dest_root: Path) -> None:
    dest_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.move(str(folder), str(dest_root / f"{stamp}_{folder.name}"))


def process_folder(client: genai.Client, browser_context, folder: Path) -> None:
    image_paths = _folder_images(folder)
    if not image_paths:
        print(f"⚠ {folder.name}: 画像が見つからないためスキップします")
        _move_folder(folder, ERROR_DIR)
        return

    print(f"\n📷 新しい商品フォルダを検出: {folder.name}（{len(image_paths)}枚）")
    try:
        image_parts = load_images(image_paths)
        result = generate_listing(client, image_parts)
        data = enrich_with_full_description(parse_result(result))
        if not data:
            print("❌ 紹介文の生成に失敗しました（JSON解析エラー）。_error に移動します。")
            _move_folder(folder, ERROR_DIR)
            return

        price = research_price(
            client,
            data.get("title", ""),
            data.get("category_suggestion", ""),
            data.get("condition", ""),
        )
        if price:
            data["price_suggestion"] = price

        try:
            append_listing_history(data)
        except OSError:
            pass

        print(f"✅ 紹介文を生成しました: {data.get('title', '')}")
        fill_mercari_listing(browser_context, image_paths, data)
        _move_folder(folder, DONE_DIR)
    except Exception as e:
        print(f"❌ 処理中にエラーが発生しました: {e}")
        _move_folder(folder, ERROR_DIR)


def main() -> None:
    load_env_file()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ GEMINI_API_KEY が設定されていません。.env を確認してください。")
        sys.exit(1)

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    client = genai.Client(api_key=api_key)

    print("🌐 ブラウザを起動しています...")
    playwright, browser_context = launch_browser()
    ensure_logged_in(browser_context)

    print(f"👀 監視中: {INBOX_DIR}")
    print("   商品ごとにサブフォルダを作り、写真を入れてください。")
    print("   例: images/inbox/デニムジャケット/ に写真を入れる")
    print("Ctrl+C で終了します。\n")

    try:
        while True:
            for entry in list(INBOX_DIR.iterdir()):
                if _is_item_folder(entry) and _folder_is_settled(entry):
                    process_folder(client, browser_context, entry)
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\n終了します。")
    finally:
        browser_context.close()
        playwright.stop()


if __name__ == "__main__":
    main()
