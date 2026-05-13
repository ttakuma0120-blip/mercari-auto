"""
メルカリ古着出品用 - 商品紹介文・タイトル自動生成ツール

写真を読み込むだけで、目を引くタイトル・購買意欲をそそる商品紹介文を出力します。
Google Gemini API（画像認識 + 文章生成）を使用しています。
"""

import os
import sys
from datetime import datetime, timedelta, timezone
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

from listing_template import (
    MAX_LISTING_CHARS,
    ai_fill_char_budget,
    build_listing_description,
    listing_base_char_count,
)

# 出力フォーマット用のプロンプト（固定レイアウト用：【ポイント】等のみ写真から生成）
_SYSTEM_CHAR_LIMIT = f"""
## 文字数制限（必須）
- 固定レイアウトに差し込んだ**商品説明文の全文**が **{MAX_LISTING_CHARS}文字以内**（1文字＝全角・半角どちらも1としてカウント）。
- 各フィールドが空のときの固定枠のみで約 **{listing_base_char_count()}** 文字。あなたが書く本文の合計は、**おおよそ {ai_fill_char_budget()} 文字以内**を目安にし、**必ず全文が{MAX_LISTING_CHARS}文字以内**になるよう調整すること。
- 長くなりそうなときは **styling_tips → points_checkmarks（✅の行を減らす）→ points_keywords** の順で短くする。素材・状態・サイズは必要最小限に。
"""

SYSTEM_PROMPT = """あなたはメルカリで古着を出品するプロのコピーライターです。
与えられた商品写真だけを根拠に、以下のJSONの各フィールドを埋めてください。

## 売れる文章の原則（全フィールド共通・必須）
- **自分ごと化**：購入者が「自分のワードローブで使える」と感じる具体性を最優先する。
- **感覚情報を入れる**：「柔らかい肌触り」「光沢感のある生地」「落ち感がある」など、手に取る前に想像できる描写を積極的に使う。
- **感情語だけ禁止**：「おしゃれ」「かわいい」「素敵」は根拠なしに単独で使わない。必ず具体的な情報と組み合わせる。
- **検索語を文章に溶かす**：メルカリで検索されやすい語（ジャンル・色・素材・年代・シルエット）を自然な文章の中に入れる。

## 重要
- 商品説明文の「レイアウト」はシステム側で固定されており、あなたが書くのは JSON の値だけです。
- 【ポイント】【着こなし】【カラー】【素材】【状態】【サイズ】の内容を、写真から読み取れる範囲で具体的に記載してください。
- 推測は「〜のように見えます」と明記し、断定しすぎないでください。
- 購入検討者が比較しやすいよう、サイズ感・シルエット・着用イメージ・状態の情報密度を優先し、冗長な言い回しは避けること。
- 価格提案（price_suggestion）は別欄として出力し、商品説明文レイアウトには混ぜないこと。

## タイトル（title）について
- タイトルにブランド名を含める場合は、タグ・ロゴに**写っている綴りをそのまま**（翻訳・カタカナ変換しない）。
- 商品名が断定できない場合は、無理にモデル名を作らず「アイテム種別 + 色 + ディテール + テイスト/ジャンル語」で構成する。
- 30文字以内で、検索されやすい語を優先して情報を圧縮する（不要な助詞や重複語は削る）。
- ジャンル・テイスト語は写真に合うものを積極的に入れる。例：90s、80s、00s、Y2K、グランジ、ロック、パンク、モード、ストリート、アメカジ、ノームコア、韓国系、フェアリーグランジ。

## points_checkmarks（✅の行）について ※重要
ユーザーメッセージに **【出品・生成の基準日時（日本時間）】** が付くので、その**日時点**の情報を使うこと。
各行は必ず **✅** で始める（2〜4行）。次の3要素を各行に振り分けること：

1. **購入の決め手になる"具体的強み"**（必ず1行以上）
   - 写真から見える最大の魅力（シルエット・サイズ感・色・素材・状態・希少性）を具体的に1行で。
   - 数字・固有名詞・シーン名を積極的に使う。「どんな人に合うか」「どう着ると映えるか」を入れる。
   - ✅ 良い例：「ゆったりXLサイズ感で肩幅広めの方にもフィット、インナー重ね着にも◎」
   - ❌ NG例：「とてもおしゃれな一枚です」（根拠なし感情語のみ）

2. **トレンド・今刺さる理由**
   そのアイテムのカテゴリ（ニット・デニム・Y2K等）について、**当時点でメルカリ・古着界隈でよく検索される・話題になりやすい観点**を1行以上に織り込む（「〜系コーデのトレンドとも相性◎」など。**根拠のない断定はせず**自然な表現で）。

3. **季節・投稿タイミング**
   - 基準日時の**季節（春夏秋冬）**と、写真から読み取れる**服の季節感**を照らし合わせる。
   - **一致・近い場合** … 「この時期のコーデに」など自然な季節フレーズを入れてよい。
   - **服と季節がズレる場合** … 「来シーズンに向けて」「まだ寒い日に」など無理のない言い方、または季節に触れず魅力だけ書く。
   - **無理に入れると嘘・違和感になる場合** … その✅行では季節に触れない（トレンド・素材・シーン・状態だけにする）。

## price_suggestion（価格設定）について ※重要
- 価格提案は必ず **price_suggestion** に1つの文章で出力する（商品説明文には入れない）。
- まず **ブランド名が判別できる場合はそのブランドの同系統アイテム相場を最優先** に考える。
- ブランドが判別できない場合は、カテゴリ・素材・デザイン・状態・サイズ感が近い **類似商品の相場** を基準にする。
- 価格は次の順で短く明記する：
  1) 推奨出品価格（まずこの金額で出す）  
  2) 売れやすい価格帯（下限〜上限）  
  3) 根拠（ブランド優先 or 類似品基準、状態・素材・希少性の要点）
- 相場は断定せず「〜円前後が狙いやすい」「〜円台が比較されやすい」など自然な表現にする。

## styling_tips（【着こなし・おすすめコーデ】の本文）について ※重要
購入者が「このアイテムを持っている生活」を具体的にイメージできる2〜4行を書く。

書き方の順（自然に組み合わせる）：
1. **刺さるシーンから入る**：「休日の軽いお出かけに〜」「デイリーのカジュアルコーデに〜」など
2. **コーデのヒント**：「ワイドパンツ・スカートと合わせると〜」「インナーにTシャツを見せて〜」など具体的に
3. **サイズ感・着こなしの幅**：「ゆったり羽織るか、タックインしてキレイめにも」など汎用性を伝える
4. **採寸確認の後押し**：「平置き実寸とお手持ちの服を比べてお選びください」など購入を自然に促す

禁止：「とても素敵です」「大変おすすめです」などの根拠のない感情語のみの文。必ず具体的な情報と組み合わせる。
長さの目安：**2〜4行**。**全文1000字以内**に収まるよう1行を短く。箇条書き記号は使わず、文章で。

## 出力形式（必ずこのJSON形式のみ。説明文は不要）
```json
{
  "title": "メルカリ用タイトル（30文字以内。アイテム・色・特徴を詰める。ブランドを入れる場合はタグ表記どおり）",
  "category_suggestion": "例：レディース > トップス > カーディガン",
  "price_suggestion": "価格設定の別欄。例：推奨出品価格 4,980円 / 売れやすい価格帯 4,300〜5,300円 / ブランド相場を優先し、状態とデザイン性を加味",
  "keywords": ["検索向け短いキーワード", "2つ目", "3つ目"],
  "points_keywords": "【ポイント】直下の1行目。スペース区切りで、ニット・柄・テイストなど検索されそうな語を並べる（例：モヘア　ニット　カーディガン　シャギー　アメカジ）",
  "points_checkmarks": "✅2〜4行。改行区切り。各服の魅力に加え、(1)当時点のトレンド・検索されやすさ (2)基準日時の季節と服の季節の整合（無理なら季節は書かない）を反映",
  "styling_tips": "【着こなし・おすすめコーデ】用。2〜4行。着こなし・合わせるアイテムの雰囲気・シーンのイメージ（写真の根拠の範囲で）。全文1000字以内に収める",
  "color": "【カラー】の本文のみ。色名を並べる（例：ブラウン　カーキ　ベージュ）",
  "material": "【素材】の本文のみ。タグが写っていればその表記。なければ感触からの推測とし、最後に改行して「※タグがないため感触からの推測」のような注記を付けてよい",
  "condition": "【状態】の本文のみ。一文（例：目立った傷や汚れはありません／全体的に使用感あり など）",
  "size_block": "【サイズ】ブロック内「↓平置き実寸（単位はcm）」の下にそのまま使う。肩幅・身幅・袖丈・着丈は各行1項目。写真やタグから数値が読めるときは「肩幅 45cm」のように記載。読めない項目は「肩幅:」「身幅:」のように**ラベルとコロン（全角「：」または半角「:」）だけ**で終え、**「要採寸」「（要採寸）」などの文言は書かない**（後から数値を追記しやすくするため）。また styling_tips か points_checkmarks のどこかで、採寸確認の価値（手持ち服との比較）を自然に一言入れてよい"
}
```

## 補足
- points_checkmarks には必ず ✅ を各行の先頭に付ける。
- 写真が複数ある場合は総合して判断する。
- 季節・トレンドは「ユーザーメッセージ末尾の基準日時」を必ず参照すること。

写真が複数ある場合は、すべての写真を総合的に判断してください。
""" + _SYSTEM_CHAR_LIMIT


def enrich_with_full_description(data: dict | None) -> dict | None:
    """固定テンプレート用JSONなら description_full を組み立てる"""
    if not data:
        return None
    if "points_keywords" in data or "size_block" in data:
        for k in (
            "points_keywords",
            "points_checkmarks",
            "styling_tips",
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


def _jst_now_context() -> str:
    """日本時間の現在日時（季節・トレンド文の基準）"""
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst)
    # 季節の目安（北日本向けのざっくり表現でAIの補助に）
    m = now.month
    if m in (3, 4, 5):
        season = "春"
    elif m in (6, 7, 8):
        season = "夏"
    elif m in (9, 10, 11):
        season = "秋"
    else:
        season = "冬"
    return (
        f"\n\n【出品・生成の基準日時（日本時間）】{now.strftime('%Y年%m月%d日 %H:%M')} "
        f"（この時点の季節の目安: {season}）\n"
        "この日時を前提に、points_checkmarks の✅行でトレンド感と季節の整合を取ること。"
    )


def generate_listing(client: genai.Client, image_parts: list[types.Part]) -> str:
    """画像から商品紹介JSONテキストを生成（Gemini のみ・画像＋文章を1回で生成）"""
    user_content = (
        "上記の商品写真を分析し、メルカリ出品用の情報を生成してください。"
        "必ず指定されたJSON形式で出力してください。"
        "price_suggestion はGoogle検索で現在のメルカリ相場・ブランド相場を調べてから算出すること。"
        + _jst_now_context()
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
    return response.text or ""


def research_price(client: genai.Client, title: str, category: str, condition: str) -> str:
    """グラウンディングでメルカリ相場をリアルタイム調査して価格提案文を返す"""
    query = (
        f"商品: {title or category}\n"
        f"カテゴリ: {category}\n"
        f"状態: {condition}\n\n"
        "上記の古着商品について、現在のメルカリでの相場をGoogle検索で調べ、"
        "推奨出品価格・売れやすい価格帯・価格根拠を1〜2文で簡潔に答えてください。"
    )
    try:
        response = client.models.generate_content(
            model=get_gemini_model(),
            contents=query,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.3,
            ),
        )
        if response.text:
            return response.text.strip()
        parts = response.candidates[0].content.parts
        texts = [p.text for p in parts if hasattr(p, "text") and p.text]
        return "\n".join(texts).strip()
    except Exception:
        return ""


def parse_result(result: str) -> dict | None:
    """結果をパースして辞書で返す。失敗時はNone"""
    import json
    import re

    if not result:
        return None

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
    print(f"\n【価格設定（提案）】 {data.get('price_suggestion', '')}")
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
