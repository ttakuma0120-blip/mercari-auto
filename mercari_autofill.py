"""
メルカリ出品フォームの自動入力（Playwright）。

写真アップロード・カテゴリー・商品の状態・商品名・商品説明・価格まで自動入力し、
最後の「出品する」ボタンは押さない（人が内容を確認してから押す）。

事前準備:
  1. playwright install chromium   （初回のみ）
  2. 初回起動時にブラウザウィンドウが開くので、そこでメルカリに手動ログインする
     （ログイン情報は playwright_profile/ にブラウザプロファイルとして保存され、
       次回以降は自動的にログイン済み状態になる）
"""

import re
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright

PROFILE_DIR = Path(__file__).parent / "playwright_profile"

CONDITION_LABELS = [
    "新品、未使用",
    "未使用に近い",
    "目立った傷や汚れなし",
    "やや傷や汚れあり",
    "傷や汚れあり",
    "全体的に状態が悪い",
]


def launch_browser():
    """
    常設ブラウザプロファイルでPlaywrightを起動する（ログイン状態を維持するため）。
    メルカリ側のBot検知でログイン画面が読み込まれなくなる事象を避けるため、
    Chromium同梱版ではなく実際のGoogle Chromeを使い、navigator.webdriver等の
    自動操作の痕跡を隠すinit scriptを注入する。
    """
    playwright = sync_playwright().start()
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        channel="chrome",
        headless=False,
        viewport={"width": 1400, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
    )
    context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = window.chrome || { runtime: {} };
        Object.defineProperty(navigator, 'languages', { get: () => ['ja-JP', 'ja'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        """
    )
    return playwright, context


def ensure_logged_in(context: BrowserContext) -> None:
    """
    初回起動時にログイン猶予を作る。
    メルカリのログイン状態はページ内で判定しづらいため、確実な自動判定はせず、
    開いたブラウザで手動ログインする時間を確保するだけにしている
    （未ログインのまま監視が始まっても、以降の自動入力が失敗するだけで実害はない）。
    """
    page = context.new_page()
    page.goto("https://jp.mercari.com/mypage/listings", wait_until="domcontentloaded")
    print("🔑 開いたブラウザのタブでメルカリにログイン済みか確認してください。")
    print("   未ログインの場合はここでログインしてください（15秒後に自動で進みます）。")
    page.wait_for_timeout(15000)
    page.close()


def map_condition_to_label(condition_text: str) -> str:
    """Geminiが生成した状態の説明文を、メルカリの「商品の状態」選択肢に対応付ける"""
    t = condition_text or ""
    if "新品" in t and "未使用" in t:
        return "新品、未使用"
    if "未使用に近い" in t:
        return "未使用に近い"
    if "全体的" in t and "悪い" in t:
        return "全体的に状態が悪い"
    if "やや" in t and ("傷" in t or "汚れ" in t):
        return "やや傷や汚れあり"
    if "目立った" in t and "なし" in t:
        return "目立った傷や汚れなし"
    if "傷" in t or "汚れ" in t:
        return "傷や汚れあり"
    return "目立った傷や汚れなし"


_COLOR_KEYWORD_MAP = [
    ("ブラック", "ブラック系"), ("黒", "ブラック系"),
    ("ホワイト", "ホワイト系"), ("白", "ホワイト系"),
    ("グレー", "グレイ系"), ("グレイ", "グレイ系"), ("灰", "グレイ系"),
    ("ベージュ", "ベージュ系"),
    ("ブラウン", "ブラウン系"), ("茶", "ブラウン系"),
    ("レッド", "レッド系"), ("赤", "レッド系"),
    ("ピンク", "ピンク系"),
    ("パープル", "パープル系"), ("紫", "パープル系"),
    ("ネイビー", "ネイビー系"), ("紺", "ネイビー系"),
    ("ブルー", "ブルー系"), ("青", "ブルー系"),
    ("グリーン", "グリーン系"), ("緑", "グリーン系"),
    ("カーキ", "カーキ系"),
    ("イエロー", "イエロー系"), ("黄", "イエロー系"),
    ("オレンジ", "オレンジ系"),
    ("ゴールド", "ゴールド系"), ("金", "ゴールド系"),
    ("シルバー", "シルバー系"), ("銀", "シルバー系"),
]


def map_color_to_mercari_categories(color_text: str) -> list[str]:
    """Geminiが生成した色名の文章から、メルカリの「カラー」選択肢（○○系）候補を推定する"""
    t = color_text or ""
    found = []
    for keyword, category in _COLOR_KEYWORD_MAP:
        if keyword in t and category not in found:
            found.append(category)
    return found


def map_condition_to_damage_flag(condition_text: str) -> str:
    """Geminiが生成した状態の説明文から、メルカリの「汚れ・破れ・臭いなど」（あり/なし）を推定する"""
    t = condition_text or ""
    if "新品" in t and "未使用" in t:
        return "なし"
    if "傷" in t or "汚れ" in t or "臭い" in t:
        if "なし" in t or "ありません" in t:
            return "なし"
        return "あり"
    if "使用感" in t or "悪い" in t:
        return "あり"
    return "なし"


def _extract_leaf_category(category_suggestion: str) -> str:
    """「レディース > トップス > カーディガン」→ 末尾の「カーディガン」を検索語にする"""
    parts = [p.strip() for p in (category_suggestion or "").split(">") if p.strip()]
    return parts[-1] if parts else ""


def _extract_price_number(price_suggestion: str) -> int | None:
    """price_suggestion の文章から推奨出品価格の数値だけを取り出す"""
    if not price_suggestion:
        return None
    m = re.search(r"推奨出品価格\D{0,6}?([\d,]{3,})\s*円", price_suggestion)
    if not m:
        m = re.search(r"([\d,]{3,})\s*円", price_suggestion)
    if not m:
        return None
    try:
        n = int(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return max(300, min(n, 9_999_999))


def _dismiss_modal_if_present(page: Page) -> None:
    try:
        close_btn = page.get_by_text("閉じる", exact=True)
        if close_btn.count() > 0:
            close_btn.first.click(timeout=2000)
    except Exception:
        pass


def _ensure_on_create_page(page: Page) -> None:
    """カテゴリー/状態選択が想定外に失敗した場合、出品フォームに戻す"""
    if not page.url.rstrip("/").endswith("/sell/create"):
        try:
            page.go_back(wait_until="domcontentloaded", timeout=5000)
        except Exception:
            pass


def _select_category(page: Page, category_suggestion: str) -> bool:
    leaf = _extract_leaf_category(category_suggestion)
    if not leaf:
        return False
    try:
        page.locator('[data-testid="category-link"] a').click()
        page.wait_for_url("**/sell/categories", timeout=5000)
        search = page.get_by_placeholder("カテゴリー名を検索")
        search.click()
        search.fill(leaf)
        page.wait_for_timeout(900)
        page.locator('button[class*="rowButton"]').first.click(timeout=5000)
        page.wait_for_url("**/sell/create", timeout=5000)
        return True
    except Exception as e:
        print(f"⚠ カテゴリーの自動選択に失敗しました（後で手動で選んでください）: {e}")
        return False
    finally:
        _ensure_on_create_page(page)


def _select_condition(page: Page, condition_text: str) -> bool:
    label = map_condition_to_label(condition_text)
    try:
        page.locator('[data-testid="item-condition"] a').click()
        page.wait_for_url("**/sell/conditions", timeout=5000)
        row = page.locator("main ul a").filter(has_text=re.compile("^" + re.escape(label)))
        row.first.click(timeout=5000)
        page.wait_for_url("**/sell/create", timeout=5000)
        return True
    except Exception as e:
        print(f"⚠ 商品の状態の自動選択に失敗しました（後で手動で選んでください）: {e}")
        return False
    finally:
        _ensure_on_create_page(page)


def _upload_photos(page: Page, image_paths: list[str]) -> None:
    page.locator('input[data-testid="photo-upload"]').set_input_files(image_paths)
    page.wait_for_timeout(2000)


def _fill_text_fields(page: Page, title: str, description_full: str) -> None:
    page.fill('input[name="name"]', (title or "").strip()[:40])
    page.fill('textarea[name="description"]', (description_full or "").strip()[:1000])


def _select_fixed_price_and_fill(page: Page, price_suggestion: str) -> None:
    try:
        page.locator('[data-testid="set-price-option"]').click(timeout=3000)
    except Exception:
        pass
    price = _extract_price_number(price_suggestion)
    if price is not None:
        try:
            page.fill('input[data-testid="price-text-input"]', str(price))
        except Exception as e:
            print(f"⚠ 価格の自動入力に失敗しました（後で手動で入力してください）: {e}")


def fill_mercari_listing(context: BrowserContext, image_paths: list[str], data: dict) -> Page:
    """
    生成済みの出品データをメルカリの出品フォームに自動入力する。
    「出品する」ボタンは押さない（最終確認・送信は人が行う）。
    """
    page = context.new_page()
    page.goto("https://jp.mercari.com/sell/create", wait_until="domcontentloaded")
    _dismiss_modal_if_present(page)

    # 先にカテゴリー/状態を選ぶと、メルカリ自体のAI自動入力機能が無効化され、
    # あとで入れる写真・商品名・商品説明が上書きされなくなる。
    _select_category(page, data.get("category_suggestion", ""))
    _select_condition(page, data.get("condition", ""))

    _upload_photos(page, image_paths)
    _fill_text_fields(page, data.get("title", ""), data.get("description_full", ""))
    _select_fixed_price_and_fill(page, data.get("price_suggestion", ""))

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.bring_to_front()
    print("✅ 下書きの自動入力が完了しました。内容を確認し、問題なければブラウザで「出品する」を押してください。")
    return page
