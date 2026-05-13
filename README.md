# メルカリ古着 商品紹介文自動生成ツール

写真をいくつか載せるだけで、**目を引くタイトル**・**購買意欲をそそる商品紹介文**など、メルカリ出品に必要な情報を自動で生成するPythonツールです。

> **別フォルダに「公開用」があります**（固定テンプレなし・全文を売れる文章として生成）。他者に配布する想定ならこちらを使ってください。  
> → `..\メルカリの商品紹介_公開版\`（`README.md` 参照・ポート **8502**）

## 生成される内容

| 項目 | 説明 |
|------|------|
| タイトル | 30文字以内の目を引くタイトル |
| 商品紹介文 | 200〜400文字の購買意欲をそそる説明文 |
| 推奨カテゴリ | メルカリのカテゴリ候補 |
| 状態の補足 | 写真から分かる状態情報 |
| 検索キーワード | 検索されそうなキーワード |

---

## 必要なもの

### 1. Python 3.10 以上

```powershell
python --version
```

### 2. Google Gemini API キー（必須）

画像の解析・文章生成の両方に **Gemini API** を使います。

---

## APIキーの取得方法（詳解）

### ステップ1: Google AI Studio にアクセス

1. ブラウザで以下にアクセスします：
   - **https://aistudio.google.com/apikey**

2. Googleアカウントでログインします。

### ステップ2: APIキーを作成

1. 「Create API key」または「APIキーを作成」をクリック
2. 既存のGoogle Cloudプロジェクトを選択するか、「Create API key in new project」で新規作成
3. 生成されたAPIキーが表示されます（例: `AIzaSy...` で始まる長い文字列）

### ステップ3: APIキーをコピー

- **重要**: このキーは一度しか表示されない場合があります。必ずコピーして安全な場所に保存してください。
- 他人に共有しないでください。

### ステップ4: 料金・無料枠について

| 項目 | 内容 |
|------|------|
| 無料枠 | モデル・プランにより異なります（公式の [料金](https://ai.google.dev/pricing) を参照） |
| 料金 | 無料枠を超えると従量課金（詳細は [Google AI 料金](https://ai.google.dev/pricing) を参照） |
| 個人利用 | 通常の出品頻度なら無料枠内で十分 |

---

## セットアップ手順

### 1. リポジトリのクローン or フォルダに移動

```powershell
cd "c:\〇AIエンジニア\試み\メルカリの商品紹介"
```

### 2. 仮想環境の作成（推奨）

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. パッケージのインストール

```powershell
pip install -r requirements.txt
```

### 4. APIキーの設定

`.env.example` をコピーして `.env` を作成し、APIキーを記述します。

```powershell
copy .env.example .env
```

`.env` を開いて編集：

```
GEMINI_API_KEY=AIzaSy...（あなたのAPIキー）
```

**注意**: `.env` はGitにコミットしないでください（`.gitignore` に含まれています）。

---

## 使い方

### 方法1: Webフロントエンド（推奨）

画像をドラッグ＆ドロップでアップロードできるWebアプリです。

```cmd
install.bat      ← 初回のみ：パッケージインストール
start_app.bat    ← Webアプリを起動（黒いウィンドウが残る）
launch_quick.bat ← おすすめ：裏でStreamlit起動→ブラウザだけ開く（ワンクリック）
```

ブラウザが開き、http://localhost:8501 で操作できます。

### ワンクリックで使いたいとき（`launch_quick.bat`）

**ブラウザのアドレス欄に URL だけ打っても、Streamlit が動いていなければ表示できません**（どこかでサーバーを起動する必要があります）。

代わりに **`launch_quick.bat` をダブルクリック**（またはショートカットをデスクトップに置く）すると次のように動きます。

- **8501 が空いていれば** … ウィンドウを出さずに Streamlit を裏起動し、数秒後にブラウザで `http://localhost:8501/` を開く
- **すでに起動済みなら** … ブラウザを開くだけ（二重起動しにくい）

終了するときは **タスクマネージャー** で `streamlit` や `python` を終了するか、従来どおり `start_app.bat` のコンソールを閉じる方法を使ってください。

1. 写真をアップロード（複数枚可）
2. 「商品紹介文を生成」ボタンをクリック
3. タイトル・紹介文などをコピーしてメルカリに貼り付け

### 方法2: コマンドラインから実行

```powershell
run.bat images\item1.jpg images\item2.jpg
```

### 例

```powershell
# 1枚だけ
run.bat images\item_front.jpg

# 複数枚（表・裏・タグなど）
run.bat images\front.jpg images\back.jpg images\tag.jpg
```

---

## 対応画像形式

- `.jpg` / `.jpeg`
- `.png`
- `.webp`
- `.gif`

---

## トラブルシューティング

### `404 NOT_FOUND` / 「gemini-2.0-flash は新規ユーザーには利用できなくなりました」

Google が **Gemini 2.0 Flash** を段階的に廃止しており、**新規に作った API キーでは 2.0 が使えない**場合があります。

このプロジェクトの**デフォルトは `gemini-2.5-flash`** に更新済みです。コードを最新のままにして再実行してください。

別モデルを試す場合は `.env` に例えば次を書きます。

```env
GEMINI_MODEL=gemini-2.5-flash
```

利用可能なモデル一覧は [Gemini モデル](https://ai.google.dev/gemini-api/docs/models/gemini) を参照してください。

### 「スクリプトの実行が無効になっているため」エラー（PowerShell）

PowerShell で `Activate.ps1` を実行できない場合、以下のいずれかを使ってください。

**方法A: バッチファイルを使う（推奨・Activate不要）**
```cmd
install.bat          ← 初回のみ：パッケージインストール
run.bat images\item1.jpg   ← ツール実行
```

**方法B: 仮想環境のPythonを直接指定**
```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe mercari_listing_generator.py images\item1.jpg
```

**方法C: PowerShellの実行ポリシーを変更**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 「GEMINI_API_KEY が設定されていません」

- `.env` ファイルがプロジェクトフォルダにあるか確認
- `.env` 内の `GEMINI_API_KEY=` の後に正しいキーが入っているか確認
- キーの前後に余分なスペースや改行がないか確認

### 「APIキーが無効です」

- [Google AI Studio](https://aistudio.google.com/apikey) でキーが有効か確認
- キーを再発行して `.env` を更新

### 画像が読み込めない

- ファイルパスが正しいか確認
- 対応形式（jpg, png, webp, gif）か確認

---

## 固定レイアウトの紹介文

【ポイント】【カラー】【素材】【状態】【サイズ】の中身だけAIが写真から生成し、それ以外（注意書き・フォロー割・キーワード行など）は **`listing_template.py`** の固定文言で毎回同じになります。文言を変えたいときは `LISTING_BODY_TEMPLATE` を編集してください。

## 生成履歴

Web（`start_app.bat`）でも CLI（`run.bat`）でも、生成に成功すると **`data/listing_history.jsonl`** に1件ずつ追記されます（最大約500件で古いものから削除）。

- **Streamlit** 左サイドバーで過去の生成を一覧・表示・TXT保存・1件削除・全削除ができます。
- 履歴ファイルは **`.gitignore` に含まれている**ため、Git にはコミットされません（バックアップしたい場合は手元でコピーしてください）。

## ファイル構成

```
メルカリの商品紹介/
├── mercari_listing_generator.py   # メインスクリプト
├── listing_template.py            # 固定レイアウト（編集可）
├── launch_quick.bat               # ワンクリック起動（裏でStreamlit＋ブラウザ）
├── launch_quick.ps1               # 上記から呼ばれるPowerShell
├── app.py                         # Webフロント（Streamlit）
├── history_store.py               # 履歴の保存・読込
├── requirements.txt               # 依存パッケージ
├── .env.example                   # 環境変数テンプレート
├── .env                           # APIキー（要作成・Gitに含めない）
├── run_example.bat                # Windows用実行バッチ
├── images/                        # 画像を置くフォルダ（任意）
├── data/listing_history.jsonl     # 生成履歴（自動作成・Git対象外）
└── README.md                      # このファイル
```

---

## ライセンス・注意事項

- 生成された文章は参考としてご利用ください。出品前に必ず内容を確認・編集してください。
- 生成内容はAIによるもので、誤りがある可能性があります。
- APIの利用規約に従ってご利用ください。
