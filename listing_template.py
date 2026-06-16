"""
メルカリ商品説明文の固定レイアウト（ユーザー指定テンプレート）
【ポイント】【カラー】【素材】【状態】【サイズ】以外は毎回同じ文言を使用します。
"""

# プレースホルダー: {points_keywords} {points_checkmarks} {color} {material} {condition} {size_block}

LISTING_BODY_TEMPLATE = """【ポイント】
{points_keywords}

{points_checkmarks}

★必ず以下を確認の上ご購入をよろしくお願いいたします★

・当店の商品は古着ですので、すべて"実寸サイズ"を基に表記サイズを記載しております。必ず実寸サイズをご確認の上ご購入くださいませ。

・写真は実物をスマホで撮影しております！

・全商品厳選した一点物になります。

・原則1～2日で発送しております。

【カラー】{color}

【素材】{material}

【状態】{condition}

【サイズ】
↓平置き実寸（単位はcm）
{size_block}

\\フォロー割/
・3,501円〜5,000円 → 200円OFF  
・5,001円〜10,000円 → 300円OFF  
・10,001円〜 → 500円OFF  
※ご購入前に「フォロー割希望」とコメントください

70's 80's 90's 00's
デザイン 個性的 色落ち パッチワーク
加工 ダメージ かすれ ワッフル ロゴ
編み込み レースアップ ギミック ブリーチ 
ミリタリー クラッシュアメカジ グランジ 
パンク Y2K モード アーカイブ ビンテージ　archive vintage
好きな方におすすめです！"""


def build_listing_description(data: dict) -> str:
    """AIが返したJSONから、固定テンプレートに差し込んだ全文を組み立てる"""
    return LISTING_BODY_TEMPLATE.format(
        points_keywords=data.get("points_keywords", "").strip(),
        points_checkmarks=data.get("points_checkmarks", "").strip(),
        color=data.get("color", "").strip(),
        material=data.get("material", "").strip(),
        condition=data.get("condition", "").strip(),
        size_block=data.get("size_block", "").strip(),
    )
