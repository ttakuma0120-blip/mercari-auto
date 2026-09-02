"""
メルカリ商品説明文の固定レイアウト（ユーザー指定テンプレート）
【ポイント】【着こなし・おすすめコーデ】【カラー】【素材】【状態】【サイズ】のうち、AI生成部分以外は毎回同じ文言を使用します。
"""

# プレースホルダー: points_keywords, points_checkmarks, styling_block（中身は build 側で組み立て）
# color, material, condition, size_block

LISTING_BODY_TEMPLATE = """【ポイント】
{points_keywords}

{points_checkmarks}{styling_block}

【注意事項】
・古着・1点物につき平置き実寸を必ずご確認ください
・写真は実物に近い色味ですが光加減で多少異なります
・1〜2日以内に発送します

【カラー】{color}
【素材】{material}
【状態】{condition}

【サイズ】平置き実寸(cm)
{size_block}

\\フォロー割/
2,001〜3,500円→100円OFF / 3,501〜5,000円→200円OFF
5,001〜10,000円→300円OFF / 10,001円〜→500円OFF
※「フォロー割希望」とコメントください

70's 80's 90's 00's Y2K グランジ パンク アメカジ
ミリタリー モード ビンテージ vintage archive"""

# メルカリ説明文の目標上限（AIプロンプトと一致させる）
MAX_LISTING_CHARS = 1000

# 種類ごとの採寸項目（【サイズ】ブロックの手動入力用）
SIZE_FIELD_SETS: dict[str, list[str]] = {
    "トップス（Tシャツ・シャツなど）": ["肩幅", "身幅", "袖丈", "着丈"],
    "ズボン": ["ウエスト", "ヒップ", "股上", "股下", "わたり幅", "裾幅"],
    "スカート": ["ウエスト", "ヒップ", "総丈", "裾幅"],
}


def build_size_block(category_key: str, measurements: dict[str, str]) -> str:
    """採寸フォームの入力値から【サイズ】ブロックの本文を組み立てる（未入力の項目はラベルのみ）"""
    fields = SIZE_FIELD_SETS.get(category_key, [])
    lines = []
    for label in fields:
        value = (measurements.get(label) or "").strip()
        lines.append(f"{label} {value}cm" if value else f"{label}：")
    return "\n".join(lines)

_STYLING_HEAD = "\n\n【着こなし・おすすめコーデ】\n"


def build_listing_description(data: dict) -> str:
    """AIが返したJSONから、固定テンプレートに差し込んだ全文を組み立てる"""
    styling = (data.get("styling_tips") or "").strip()
    if styling:
        styling_block = f"{_STYLING_HEAD}{styling}"
    else:
        styling_block = ""
    return LISTING_BODY_TEMPLATE.format(
        points_keywords=data.get("points_keywords", "").strip(),
        points_checkmarks=data.get("points_checkmarks", "").strip(),
        styling_block=styling_block,
        color=data.get("color", "").strip(),
        material=data.get("material", "").strip(),
        condition=data.get("condition", "").strip(),
        size_block=data.get("size_block", "").strip(),
    )


def listing_base_char_count() -> int:
    """AIフィールドがすべて空のときの本文文字数（着こなし見出しなし）"""
    return len(
        build_listing_description(
            {
                "points_keywords": "",
                "points_checkmarks": "",
                "styling_tips": "",
                "color": "",
                "material": "",
                "condition": "",
                "size_block": "",
            }
        )
    )


def ai_fill_char_budget() -> int:
    """
    全文が MAX_LISTING_CHARS 以内に収まるよう、AIが埋める本文の目安上限。
    着こなし見出し（固定）分を差し引く。
    """
    overhead = len(_STYLING_HEAD)
    return max(80, MAX_LISTING_CHARS - listing_base_char_count() - overhead)
