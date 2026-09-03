"""
メルカリ商品紹介文生成 - Webフロントエンド

画像をドラッグ＆ドロップまたはアップロードして、商品紹介文を生成します。
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from history_store import (
    append_listing_history,
    clear_all_history,
    delete_entry,
    load_history,
)
from listing_template import SIZE_FIELD_SETS, build_listing_description, build_size_block
from mercari_autofill import (
    _extract_leaf_category,
    _extract_price_number,
    map_color_to_mercari_categories,
    map_condition_to_damage_flag,
    map_condition_to_label,
)
from mercari_listing_generator import (
    enrich_with_full_description,
    generate_listing,
    load_env_file,
    parse_result,
    research_price,
    uploaded_files_to_parts,
)
from google import genai

# .env を読み込み（ローカル用）。Streamlit Cloud では st.secrets から補完する
load_env_file()
if not os.getenv("GEMINI_API_KEY") and "GEMINI_API_KEY" in st.secrets:
    os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]

st.set_page_config(
    page_title="メルカリ商品紹介文生成",
    page_icon="📦",
    layout="wide",
)

# スマホ幅（iPhone等）で見出し・本文の文字が相対的に大きくなりすぎるのを抑える
st.markdown(
    """
    <style>
    @media (max-width: 600px) {
        h1 { font-size: 1.5rem !important; }
        h2 { font-size: 1.2rem !important; }
        h3 { font-size: 1.05rem !important; }
        [data-testid="stMarkdownContainer"] p,
        [data-testid="stCaptionContainer"] { font-size: 0.9rem !important; }
        .stButton button, .stDownloadButton button,
        .stLinkButton a, .stLinkButton button {
            font-size: 0.85rem !important;
            padding: 0.35rem 0.6rem !important;
        }
        input, textarea { font-size: 0.9rem !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# アプリ内パスワードゲート（ブラウザのHTTP Basic認証はスマホ端末によって
# ポップアップが出ないことがあるため、こちらを正としてアクセス制限する）。
# ログイン状態はURLのクエリパラメータで持たせる
# （session_stateだけだとページの完全リロードで消えてしまうため）。
_app_password = os.getenv("APP_ACCESS_PASSWORD")
if _app_password:
    if st.query_params.get("key") != _app_password:
        st.title("🔒 ログイン")
        pw = st.text_input("パスワード", type="password", key="app_login_pw")
        if st.button("入る", type="primary"):
            if pw == _app_password:
                st.query_params["key"] = pw
                st.rerun()
            else:
                st.error("パスワードが違います。")
        st.stop()

# 生成結果を再実行後も保持（ダウンロード等で消えない）
if "current_listing" not in st.session_state:
    st.session_state.current_listing = None
if "last_parse_failed_raw" not in st.session_state:
    st.session_state.last_parse_failed_raw = None
if "listing_version" not in st.session_state:
    st.session_state.listing_version = 0
if "upload_widget_id" not in st.session_state:
    st.session_state.upload_widget_id = 0


def clipboard_copy_button(label: str, text: str, dom_key: str) -> None:
    """紹介文・タイトルをクリップボードにコピー（UTF-8対応）"""
    safe = "".join(c if c.isalnum() else "_" for c in dom_key)[-60:]
    b64 = base64.b64encode((text or "").encode("utf-8")).decode("ascii")
    components.html(
        f"""
        <div style="font-family: sans-serif;">
        <button type="button" id="cp_{safe}" style="
            padding: 0.4rem 0.85rem;
            border-radius: 0.35rem;
            border: 1px solid #ccc;
            background: #f0f2f6;
            cursor: pointer;
        ">📋 {label}</button>
        <span id="ok_{safe}" style="margin-left:8px;color:#2e7d32;font-size:12px;"></span>
        <script>
        (function() {{
            const b64 = "{b64}";
            document.getElementById("cp_{safe}").addEventListener("click", function() {{
                const bin = atob(b64);
                const bytes = new Uint8Array(bin.length);
                for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
                const t = new TextDecoder("utf-8").decode(bytes);
                navigator.clipboard.writeText(t).then(function() {{
                    const el = document.getElementById("ok_{safe}");
                    el.textContent = "コピーしました";
                    setTimeout(function() {{ el.textContent = ""; }}, 2000);
                }});
            }});
        }})();
        </script>
        </div>
        """,
        height=52,
    )


def _launch_mercari_autofill(uploaded_files, listing_data: dict) -> None:
    """
    現在の出品データをメルカリの出品フォームに自動入力する。
    Playwright(同期API)はStreamlitのイベントループと競合するため、別プロセスで実行する。
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="mercari_fill_"))
    image_paths = []
    for f in uploaded_files:
        f.seek(0)
        img_path = tmp_dir / f.name
        img_path.write_bytes(f.read())
        image_paths.append(str(img_path))
        f.seek(0)

    payload_path = tmp_dir / "payload.json"
    payload_path.write_text(
        json.dumps({"image_paths": image_paths, "data": listing_data}, ensure_ascii=False),
        encoding="utf-8",
    )

    script_path = Path(__file__).parent / "mercari_fill_cli.py"
    subprocess.Popen(
        [sys.executable, str(script_path), str(payload_path)],
        cwd=str(Path(__file__).parent),
    )


def render_listing_result(data: dict, key_prefix: str = "main") -> None:
    """生成結果ブロックを表示（タイトル・紹介文は編集可）"""
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📝 タイトル（30文字以内・編集可）")
        st.text_input(
            "タイトル",
            key="main_title_editor",
            max_chars=30,
            label_visibility="collapsed",
            placeholder="タイトルを入力",
        )
        title_export = st.session_state.get(
            "main_title_editor", data.get("title", "")
        )
        cta, ctb = st.columns(2)
        with cta:
            clipboard_copy_button(
                "タイトルをコピー", title_export, f"{key_prefix}_title_cp"
            )
        with ctb:
            st.download_button(
                "TXTで保存",
                title_export,
                key=f"{key_prefix}_dl_title",
                file_name="mercari_title.txt",
                mime="text/plain",
                use_container_width=True,
            )

    with col2:
        st.subheader("📂 推奨カテゴリ")
        st.text(data.get("category_suggestion", ""))

        st.subheader("💰 価格設定（提案）")
        st.text(data.get("price_suggestion", ""))

        st.subheader("🏷️ 検索キーワード")
        keywords = data.get("keywords", [])
        if keywords:
            st.caption(", ".join(keywords))

    st.subheader("📄 商品紹介文（固定レイアウト全文・編集可）")
    st.text_area(
        "紹介文",
        height=420,
        key="main_description_editor",
        label_visibility="collapsed",
        placeholder="紹介文を入力・修正",
    )
    desc_export = st.session_state.get(
        "main_description_editor",
        data.get("description_full", data.get("description", "")),
    )
    c1, c2 = st.columns(2)
    with c1:
        clipboard_copy_button(
            "紹介文をコピー", desc_export, f"{key_prefix}_desc_cp"
        )
    with c2:
        st.download_button(
            "紹介文をTXTで保存",
            desc_export,
            key=f"{key_prefix}_dl_desc",
            file_name="mercari_description.txt",
            mime="text/plain",
            use_container_width=True,
        )

    st.divider()
    st.subheader("📋 メルカリへの貼り付けガイド（上から順にやればOK）")
    st.caption(
        "カテゴリーを選ぶと「ブランド」「サイズ」「カラー」「汚れ・破れ・臭いなど」が追加で表示されます"
        "（サイズ・カラー・汚れ等は入力必須、ブランドは任意）。"
    )
    leaf_category = _extract_leaf_category(data.get("category_suggestion", ""))
    condition_label = map_condition_to_label(data.get("condition", ""))
    price_number = _extract_price_number(data.get("price_suggestion", ""))
    color_categories = map_color_to_mercari_categories(data.get("color", ""))
    damage_flag = map_condition_to_damage_flag(data.get("condition", ""))

    guide_rows = [
        {"#": 1, "メルカリの項目": "出品画像", "必須": "必須", "入力・選択する内容": "アップロードした写真をそのまま追加"},
        {"#": 2, "メルカリの項目": "商品名", "必須": "必須", "入力・選択する内容": "上の「タイトルをコピー」→ 貼り付け"},
        {
            "#": 3,
            "メルカリの項目": "カテゴリー",
            "必須": "必須",
            "入力・選択する内容": (
                f"検索欄に「{leaf_category}」と入力 → 候補を選択"
                if leaf_category
                else "内容を見て手動で選択"
            ),
        },
        {
            "#": 4,
            "メルカリの項目": "ブランド",
            "必須": "任意",
            "入力・選択する内容": (
                f"「{data.get('brand', '')}」を検索して選択"
                if data.get("brand", "").strip()
                else "分からなければ「ブランドなし」のままでOK"
            ),
        },
        {"#": 5, "メルカリの項目": "商品の状態", "必須": "必須", "入力・選択する内容": f"「{condition_label}」を選択"},
        {"#": 6, "メルカリの項目": "サイズ", "必須": "必須", "入力・選択する内容": "商品タグの表記を見て選択（下の【サイズ】欄の実寸も参考）"},
        {
            "#": 7,
            "メルカリの項目": "カラー",
            "必須": "必須",
            "入力・選択する内容": (
                "「" + "」「".join(color_categories) + "」を選択（複数選択可）"
                if color_categories
                else "下の【カラー】欄を見て選択"
            ),
        },
        {"#": 8, "メルカリの項目": "汚れ・破れ・臭いなど", "必須": "必須", "入力・選択する内容": f"「{damage_flag}」を選択（違えば商品の状態を見て変更）"},
        {"#": 9, "メルカリの項目": "商品の説明", "必須": "任意", "入力・選択する内容": "上の「紹介文をコピー」→ 貼り付け"},
        {"#": 10, "メルカリの項目": "配送料の負担", "必須": "必須", "入力・選択する内容": "初期値「送料込み(出品者負担)」のままでOK"},
        {"#": 11, "メルカリの項目": "配送の方法", "必須": "必須", "入力・選択する内容": "初期値なし。いつも使う方法を選択（毎回同じでOK）"},
        {"#": 12, "メルカリの項目": "発送元の地域", "必須": "必須", "入力・選択する内容": "初期値なし。自分の都道府県を選択（毎回同じ）"},
        {"#": 13, "メルカリの項目": "発送までの日数", "必須": "必須", "入力・選択する内容": "初期値「2〜3日で発送」のままでOK"},
        {
            "#": 14,
            "メルカリの項目": "価格",
            "必須": "必須",
            "入力・選択する内容": f"「{price_number:,}」と入力" if price_number else "上の価格設定（提案）を見て手動で入力",
        },
    ]
    st.dataframe(
        guide_rows,
        hide_index=True,
        use_container_width=True,
        column_config={
            "#": st.column_config.NumberColumn(width="small"),
            "メルカリの項目": st.column_config.TextColumn(width="medium"),
            "必須": st.column_config.TextColumn(width="small"),
            "入力・選択する内容": st.column_config.TextColumn(width="large"),
        },
    )

    gcol1, gcol2, gcol3 = st.columns(3)
    with gcol1:
        if leaf_category:
            clipboard_copy_button(
                f"「{leaf_category}」をコピー", leaf_category, f"{key_prefix}_cat_cp"
            )
    with gcol2:
        if price_number:
            clipboard_copy_button(
                f"価格 {price_number} をコピー", str(price_number), f"{key_prefix}_price_cp"
            )
    with gcol3:
        brand_value = (data.get("brand") or "").strip()
        if brand_value:
            clipboard_copy_button(
                f"「{brand_value}」をコピー", brand_value, f"{key_prefix}_brand_cp"
            )

    st.link_button(
        "🛒 メルカリの出品画面を開く",
        "https://jp.mercari.com/sell/create",
        use_container_width=True,
    )

    with st.expander("写真から生成した差し替え部分のみ"):
        st.text(f"【ポイント】キーワード行\n{data.get('points_keywords', '')}")
        st.text(f"【ポイント】✅箇条書き\n{data.get('points_checkmarks', '')}")
        st.text(f"【着こなし・おすすめコーデ】\n{data.get('styling_tips', '')}")
        st.text(f"【カラー】\n{data.get('color', '')}")
        st.text(f"【素材】\n{data.get('material', '')}")
        st.text(f"【状態】\n{data.get('condition', '')}")
        st.text(f"【サイズ】ブロック\n{data.get('size_block', '')}")


# ----- サイドバー：履歴 -----
with st.sidebar:
    st.header("📜 生成履歴")
    st.caption("保存先: `data/listing_history.jsonl`（最大500件）")
    history = load_history(80)
    if not history:
        st.info("まだ履歴がありません。下で生成すると自動保存されます。")
    else:
        labels = [
            f"{h.get('created_at', '')[:16].replace('T', ' ')} | "
            f"{(h.get('title') or '無題')[:36]}"
            for h in history
        ]
        pick = st.selectbox(
            "過去の生成を開く",
            options=list(range(len(history))),
            format_func=lambda i: labels[i],
            key="history_pick",
        )
        sel = history[pick]
        st.markdown("**タイトル**")
        st.code(sel.get("title") or "", language=None)
        st.markdown("**紹介文**")
        st.text_area(
            "紹介文",
            value=sel.get("description_full", ""),
            height=260,
            key=f"hist_desc_{sel['id']}",
        )
        st.download_button(
            "この内容をTXTで保存",
            sel.get("description_full", ""),
            file_name=f"mercari_{sel['id'][:8]}.txt",
            mime="text/plain",
            key=f"hist_dl_{sel['id']}",
            use_container_width=True,
        )
        if st.button("この履歴を削除", key=f"hist_del_{sel['id']}", use_container_width=True):
            delete_entry(sel["id"])
            st.rerun()

        st.divider()
        confirm = st.checkbox("全削除の確認にチェック", key="confirm_clear_hist")
        if st.button("履歴をすべて削除", type="secondary", disabled=not confirm):
            clear_all_history()
            st.rerun()

title_col, link_col = st.columns([5, 2])
with title_col:
    st.title("📦 メルカリ商品紹介文 自動生成")
    st.caption(
        "写真をアップロードするだけで、タイトルと【ポイント】【カラー】【素材】【状態】【サイズ】を埋めた定型紹介文を生成します（Gemini のみ）"
    )
with link_col:
    st.write("")
    st.link_button(
        "🛒 メルカリを開く",
        "https://jp.mercari.com/sell/create",
        use_container_width=True,
    )

# 画像アップロード（key に upload_widget_id を含め、クリア時にインクリメントして
# ウィジェットを作り直す → ブラウザのファイルチップ／フォルダ選択もリセットされる）
_upload_key = f"mercari_uploaded_images_{st.session_state.upload_widget_id}"
uc1, uc2 = st.columns([4, 1])
with uc1:
    uploaded_files = st.file_uploader(
        "商品の写真をアップロード（複数可）",
        accept_multiple_files=True,
        help="表・裏・タグなど複数枚あると精度が上がります（JPG/PNG/WEBP/GIF対応）",
        key=_upload_key,
    )
with uc2:
    st.write("")  # ラベル位置合わせ
    st.write("")
    if st.button(
        "🗑️ 写真を一括で削除",
        key="clear_uploaded_images_btn",
        use_container_width=True,
    ):
        st.session_state.upload_widget_id += 1
        st.rerun()

if uploaded_files:
    cols = st.columns(min(len(uploaded_files), 4))
    for i, f in enumerate(uploaded_files):
        with cols[i % 4]:
            st.image(f, caption=f.name, use_container_width=True)
        f.seek(0)  # 読み込み位置をリセット

# ブランド名（分かる場合のみ。タグに表記がなければ空欄でOK）
st.subheader("🏷️ ブランド名（分かれば入力・空欄でもOK）")
brand_name = st.text_input(
    "ブランド名",
    key="brand_name_input",
    label_visibility="collapsed",
    placeholder="例: Champion（分からなければ空欄のままでOK）",
)

# 採寸入力（生成前に分かっている数値を入れておくと、そのまま説明文に使われる）
st.subheader("📏 採寸（分かっていれば先に入力しておくと、そのまま説明文に使われます）")
size_category = st.selectbox(
    "種類", options=list(SIZE_FIELD_SETS.keys()), key="size_category_select"
)
size_fields = SIZE_FIELD_SETS[size_category]
measurements = {}
_half = (len(size_fields) + 1) // 2
size_cols = st.columns(2)
with size_cols[0]:
    for label in size_fields[:_half]:
        measurements[label] = st.text_input(
            f"{label}（cm）",
            key=f"size_input_{size_category}_{label}",
            placeholder="例: 45",
        )
with size_cols[1]:
    for label in size_fields[_half:]:
        measurements[label] = st.text_input(
            f"{label}（cm）",
            key=f"size_input_{size_category}_{label}",
            placeholder="例: 45",
        )
st.caption("未入力のままでも生成できます（あとから反映することもできます）。")

# 生成ボタン
if st.button("✨ 商品紹介文を生成", type="primary", use_container_width=True):
    if not uploaded_files:
        st.error("画像をアップロードしてください")
        st.stop()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        st.error(
            "GEMINI_API_KEY が設定されていません。.env ファイルにAPIキーを追加してください。"
        )
        st.stop()

    with st.spinner("生成中... しばらくお待ちください"):
        try:
            image_parts = uploaded_files_to_parts(uploaded_files)
            client = genai.Client(api_key=api_key)
            result = generate_listing(client, image_parts)
            data = parse_result(result)
            if data and any(v.strip() for v in measurements.values()):
                data["size_block"] = build_size_block(size_category, measurements)
            if data:
                data["brand"] = brand_name.strip()
            data = enrich_with_full_description(data)

            if data:
                with st.spinner("価格相場をリアルタイム調査中..."):
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
                # 新しい生成のたびにキーを変え、前の紹介文が残らないようにする
                st.session_state.listing_version = (
                    st.session_state.get("listing_version", 0) + 1
                )
                st.session_state.current_listing = data
                st.session_state.last_parse_failed_raw = None
                # 編集用ウィジェットの初期値（直後の表示と一致させる）
                st.session_state["main_title_editor"] = data.get("title", "")
                st.session_state["main_description_editor"] = data.get(
                    "description_full", data.get("description", "")
                )
                st.success("生成完了！履歴に保存しました。")
            else:
                st.session_state.current_listing = None
                st.session_state.last_parse_failed_raw = result
                st.warning("JSON形式で解析できませんでした。生の結果を表示します。")

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
            raise

# ----- 画面に保持した生成結果（ダウンロードしても消えない） -----
if st.session_state.current_listing:
    _d = st.session_state.current_listing
    if "main_title_editor" not in st.session_state:
        st.session_state["main_title_editor"] = _d.get("title", "")
    if "main_description_editor" not in st.session_state:
        st.session_state["main_description_editor"] = _d.get(
            "description_full", _d.get("description", "")
        )

    st.divider()
    st.info(
        "📌 **直近の生成結果** — 新しい服で「生成」に成功すると内容は**差し替わり**ます。"
        " ダウンロードやコピー後も表示は残ります（「表示を消す」で消せます）。"
    )
    if st.button(
        "📐 上の採寸欄の内容を説明文に反映（生成後に採寸を直したとき用）",
        key="apply_size_btn",
    ):
        new_block = build_size_block(size_category, measurements)
        _updated = dict(st.session_state.current_listing)
        _updated["size_block"] = new_block
        _updated["description_full"] = build_listing_description(_updated)
        st.session_state.current_listing = _updated
        # まだ作られていないウィジェット(main_description_editor)の初期値を
        # この場で書き換えているので、このrun内でそのまま反映される（st.rerun()不要）
        st.session_state["main_description_editor"] = _updated["description_full"]
        st.success("説明文の【サイズ】欄に反映しました。")

    v = st.session_state.get("listing_version", 0)
    render_listing_result(
        st.session_state.current_listing, key_prefix=f"persist_v{v}"
    )

    st.divider()
    if st.button(
        "🚀 メルカリへ自動入力（新しいウィンドウで下書きを開く）",
        key="mercari_autofill_btn",
        type="primary",
        use_container_width=True,
    ):
        if not uploaded_files:
            st.error(
                "写真が見つかりません。ページ上部で写真をアップロードした状態のまま操作してください。"
            )
        else:
            fill_data = dict(st.session_state.current_listing)
            fill_data["title"] = st.session_state.get(
                "main_title_editor", fill_data.get("title", "")
            )
            fill_data["description_full"] = st.session_state.get(
                "main_description_editor", fill_data.get("description_full", "")
            )
            with st.spinner("ブラウザでメルカリの出品フォームを開いています..."):
                _launch_mercari_autofill(uploaded_files, fill_data)
            st.success(
                "自動入力を開始しました。数秒後に新しいブラウザウィンドウが開きます。"
                "「出品する」ボタンは押されないので、内容を確認してから自分で押してください。"
            )
    st.caption(
        "写真・商品名・商品説明・カテゴリー・商品の状態・価格まで自動入力します"
        "（カテゴリー・状態・価格はベストエフォート。ブランド・サイズ等の任意項目と最終確認・出品は手動です）"
    )

    if st.button("🗑️ この結果の表示を消す", key="clear_listing_display"):
        st.session_state.current_listing = None
        st.session_state.last_parse_failed_raw = None
        for _k in ("main_title_editor", "main_description_editor"):
            if _k in st.session_state:
                del st.session_state[_k]
        st.rerun()

elif st.session_state.last_parse_failed_raw is not None:
    st.divider()
    st.warning("直近の生成で JSON を解析できませんでした（再実行まで表示）。")
    st.code(st.session_state.last_parse_failed_raw)
    if st.button("🗑️ この表示を消す", key="clear_failed_display"):
        st.session_state.last_parse_failed_raw = None
        st.rerun()
