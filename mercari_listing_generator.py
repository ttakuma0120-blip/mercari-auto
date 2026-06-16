"""
メルカリ古着出品用 - 商品紹介文・タイトル自動生成ツール

写真を読み込むだけで、目を引くタイトル・購買意欲をそそる商品紹介文を出力します。
Google Gemini API（画像認識 + 文章生成）を使用しています。
"""

import os
import sys
from pathlib import Path

# Windowsのコンソールで絵文字等のUnicode出力エラーを防ぐ
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass  # 古いPythonや特殊環境ではスキップ

from google import genai
from google.genai import types


def load_env_file() -> None:
    """プロジェクトフォルダの .env から環境変数を読み込む（dotenvパッケージ不要）"""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")


load_env_file()

from listing_template import build_listing_description

# 出力フォーマット用のプロンプト（固定レイアウト用：【ポイント】等のみ写真から生成）
SYSTEM_PROMPT = """あなたはメルカリで古着を出品するプロのライターです。
与えられた商品写真だけを根拠に、以下のJSONの各フィールドを埋めてください。

## 重要
- 商品説明文の「レイアウト」はシステム側で固定されており、あなたが書くのは JSON の値だけです。
- 【ポイント】【カラー】【素材】【状態】【サイズ】の内容だけを、写真から読み取れる範囲で具体的に記載してください。
- 推測は「〜のように見えます」と明記し、断定しすぎないでください。

## タイトル（title）について
- タイトルにブランド名を含める場合は、タグ・ロゴに**写っている綴りをそのまま**（翻訳・カタカナ変換しない）。

## 出力形式（必ずこのJSON形式のみ。説明文は不要）
```json
{
  "title": "メルカリ用タイトル（30文字以内。アイテム・色・特徴を詰める。ブランドを入れる場合はタグ表記どおり）",
  "category_suggestion": "例：レディース > トップス > カーディガン",
  "keywords": ["検索向け短いキーワード", "2つ目", "3つ目"],
  "points_keywords": "【ポイント】直下の1行目。スペース区切りで、ニット・柄・テイストなど検索されそうな語を並べる（例：モヘア　ニット　カーディガン　シャギー　アメカジ）",
  "points_checkmarks": "✅で始まる行を2〜4行。実際の改行で区切る。商品の魅力を箇条書き",
  "color": "【カラー】の本文のみ。色名を並べる（例：ブラウン　カーキ　ベージュ）",
  "material": "【素材】の本文のみ。タグが写っていればその表記。なければ感触からの推測とし、最後に改行して「※タグがないため感触からの推測」のような注記を付けてよい",
  "condition": "【状態】の本文のみ。一文（例：目立った傷や汚れはありません／全体的に使用感あり など）",
  "size_block": "【サイズ】ブロック内「↓平置き実寸（単位はcm）」の下にそのまま使う。肩幅・身幅・袖丈・着丈は各行1項目。写真やタグから数値が読めるときは「肩幅 45cm」のように記載。読めない項目は「肩幅:」「身幅:」のように**ラベルとコロン（全角「：」または半角「:」）だけ**で終え、**「要採寸」「（要採寸）」などの文言は書かない**（後から数値を追記しやすくするため）"
}
```

## 補足
- points_checkmarks には必ず ✅ を各行の先頭に付ける。
- 写真が複数ある場合は総合して判断する。

写真が複数ある場合は、すべての写真を総合的に判断してください。
"""


def enrich_with_full_description(data: dict | None) -> dict | None:
    """固定テンプレート用JSONなら description_full を組み立てる"""
    if not data:
        return None
    if "points_keywords" in data or "size_block" in data:
        for k in (
            "points_keywords",
            "points_checkmarks",
            "color",
            "material",
            "condition",
            "size_block",
        ):
            data.setdefault(k, "")
        data["description_full"] = build_listing_description(data)
    elif "description" in data:
        data["description_full"] = data["description"]
    return data


def load_images(image_paths: list[str]) -> list[types.Part]:
    """画像ファイルを読み込み、Gemini API用のPartに変換"""
    parts = []
    supported_formats = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

    for path in image_paths:
        p = Path(path)
        if not p.exists():
            print(f"⚠ ファイルが見つかりません: {path}")
            continue
        if p.suffix.lower() not in supported_formats:
            print(f"⚠ 未対応の形式です: {path}")
            continue

        with open(p, "rb") as f:
            image_bytes = f.read()

        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }
        mime_type = mime_map.get(p.suffix.lower(), "image/jpeg")

        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

    return parts


def get_gemini_model() -> str:
    """
    使用するモデルID。
    デフォルトは gemini-2.5-flash（gemini-2.0-flash は新規アカウントでは利用不可のため）。
    .env で GEMINI_MODEL=... と上書き可能。
    """
    m = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    return m or "gemini-2.5-flash"


def generate_listing(client: genai.Client, image_parts: list[types.Part]) -> str:
    """画像から商品紹介JSONテキストを生成（Gemini のみ・画像＋文章を1回で生成）"""
    user_content = (
        "上記の商品写真を分析し、メルカリ出品用の情報を生成してください。"
        "必ず指定されたJSON形式で出力してください。"
    )
    contents = image_parts + [user_content]
    response = client.models.generate_content(
        model=get_gemini_model(),
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.7,
        ),
    )
    return response.text


def parse_result(result: str) -> dict | None:
    """結果をパースして辞書で返す。失敗時はNone"""
    import json
    import re

    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", result)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        json_str = result.strip()

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None


def parse_and_display(result: str) -> None:
    """結果をパースしてコンソールに表示"""
    data = parse_result(result)
    data = enrich_with_full_description(data)
    if data is None:
        print("\n--- 生成結果（生テキスト） ---\n")
        print(result)
        return

    print("\n" + "=" * 50)
    print("📦 メルカリ出品用 生成結果")
    print("=" * 50)
    print(f"\n【タイトル】（30文字以内）")
    print(f"  {data.get('title', '')}")
    print(f"\n【商品紹介文（固定レイアウト全文）】")
    print(data.get("description_full", data.get("description", "")))
    print(f"\n【推奨カテゴリ】 {data.get('category_suggestion', '')}")
    if data.get("keywords"):
        print(f"\n【検索キーワード】 {', '.join(data['keywords'])}")
    print("\n" + "=" * 50)
    try:
        from history_store import append_listing_history

        append_listing_history(data)
        print("💾 履歴を保存しました（data/listing_history.jsonl）")
    except OSError as e:
        print(f"⚠ 履歴の保存に失敗しました: {e}")


def uploaded_files_to_parts(uploaded_files: list) -> list[types.Part]:
    """StreamlitのアップロードファイルをGemini API用のPartに変換"""
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    parts = []
    for f in uploaded_files:
        image_bytes = f.read()
        mime = getattr(f, "type", None) or mime_map.get(
            Path(f.name).suffix.lower(), "image/jpeg"
        )
        parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
    return parts


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ エラー: GEMINI_API_KEY が設定されていません。")
        print("   .env ファイルに GEMINI_API_KEY=あなたのAPIキー を追加するか、")
        print("   環境変数 GEMINI_API_KEY を設定してください。")
        print("\n   APIキーの取得方法は README.md を参照してください。")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("使い方: python mercari_listing_generator.py <画像1> [画像2] [画像3] ...")
        print("例: python mercari_listing_generator.py photo1.jpg photo2.jpg")
        sys.exit(1)

    image_paths = sys.argv[1:]
    print(f"📷 読み込み中: {len(image_paths)} 枚の画像")

    image_parts = load_images(image_paths)
    if not image_parts:
        print("❌ 有効な画像がありません。")
        sys.exit(1)

    print(f"✅ {len(image_parts)} 枚の画像を読み込みました。生成中...")

    client = genai.Client(api_key=api_key)
    result = generate_listing(client, image_parts)
    parse_and_display(result)


if __name__ == "__main__":
    main()
