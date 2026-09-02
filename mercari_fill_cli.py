"""
app.py（Streamlit）からメルカリへの自動入力を実行するための単体スクリプト。

Streamlitのプロセス内でPlaywright（同期API）を直接呼ぶとイベントループが競合するため、
別プロセスとして起動する。app.py は起動するだけで、このプロセスの終了を待たない
（ブラウザのタブを開いたまま、ユーザーが確認・出品できるようにするため）。

使い方:
  python mercari_fill_cli.py <payload.jsonのパス>

payload.json の形式:
  {"image_paths": ["C:\\...\\1.jpg", ...], "data": {...generate_listingの出力+description_full...}}
"""

import json
import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

from mercari_autofill import ensure_logged_in, fill_mercari_listing, launch_browser


def main() -> None:
    if len(sys.argv) < 2:
        print("使い方: python mercari_fill_cli.py <payload.jsonのパス>")
        sys.exit(1)

    payload_path = Path(sys.argv[1])
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    image_paths = payload["image_paths"]
    data = payload["data"]

    print("🌐 ブラウザを起動しています...")
    playwright, context = launch_browser()
    ensure_logged_in(context)

    page = fill_mercari_listing(context, image_paths, data)

    # ユーザーがタブを閉じる（＝確認・出品し終わる）までプロセスを維持する
    try:
        page.wait_for_event("close", timeout=0)
    except Exception:
        pass
    finally:
        try:
            context.close()
        except Exception:
            pass
        playwright.stop()


if __name__ == "__main__":
    main()
