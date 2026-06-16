"""
メルカリ商品紹介文生成 - Webフロントエンド

画像をドラッグ＆ドロップまたはアップロードして、商品紹介文を生成します。
"""

import base64
import os

import streamlit as st
import streamlit.components.v1 as components

from history_store import (
    append_listing_history,
    clear_all_history,
    delete_entry,
    load_history,
)
from mercari_listing_generator import (
    enrich_with_full_description,
    generate_listing,
    load_env_file,
    parse_result,
    uploaded_files_to_parts,
)
from google import genai

# .env を読み込み
load_env_file()

st.set_page_config(
    page_title="メルカリ商品紹介文生成",
    page_icon="📦",
    layout="wide",
)

# 生成結果を再実行後も保持（ダウンロード等で消えない）
if "current_listing" not in st.session_state:
    st.session_state.current_listing = None
if "last_parse_failed_raw" not in st.session_state:
    st.session_state.last_parse_failed_raw = None
if "listing_version" not in st.session_state:
    st.session_state.listing_version = 0


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

    with st.expander("写真から生成した差し替え部分のみ"):
        st.text(f"【ポイント】キーワード行\n{data.get('points_keywords', '')}")
        st.text(f"【ポイント】✅箇条書き\n{data.get('points_checkmarks', '')}")
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

st.title("📦 メルカリ商品紹介文 自動生成")
st.caption(
    "写真をアップロードするだけで、タイトルと【ポイント】【カラー】【素材】【状態】【サイズ】を埋めた定型紹介文を生成します（Gemini のみ）"
)

# 画像アップロード
uploaded_files = st.file_uploader(
    "商品の写真をアップロード（複数可）",
    type=["jpg", "jpeg", "png", "webp", "gif"],
    accept_multiple_files=True,
    help="表・裏・タグなど複数枚あると精度が上がります",
)

if uploaded_files:
    cols = st.columns(min(len(uploaded_files), 4))
    for i, f in enumerate(uploaded_files):
        with cols[i % 4]:
            st.image(f, caption=f.name, use_container_width=True)
        f.seek(0)  # 読み込み位置をリセット

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
            data = enrich_with_full_description(parse_result(result))

            if data:
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
    v = st.session_state.get("listing_version", 0)
    render_listing_result(
        st.session_state.current_listing, key_prefix=f"persist_v{v}"
    )
    if st.button("🗑️ この結果の表示を消す", key="clear_listing_display"):
        st.session_state.current_listing = None
        st.session_state.last_parse_failed_raw = None
        for _k in ("main_title_editor", "main_description_editor"):
            if _k in st.session_state:
                del st.session_state[_k]
        st.rerun()

elif st.session_state.last_parse_failed_raw:
    st.divider()
    st.warning("直近の生成で JSON を解析できませんでした（再実行まで表示）。")
    st.code(st.session_state.last_parse_failed_raw)
    if st.button("🗑️ この表示を消す", key="clear_failed_display"):
        st.session_state.last_parse_failed_raw = None
        st.rerun()
