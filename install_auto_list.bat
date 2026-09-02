@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo パッケージをインストールしています...
"%~dp0.venv\Scripts\python.exe" -m pip install -r requirements.txt

echo.
echo ブラウザ自動操作用のChromiumをインストールしています（初回のみ・数分かかります）...
"%~dp0.venv\Scripts\python.exe" -m playwright install chromium

echo.
echo 完了しました。auto_list.bat で自動出品ツールを起動できます。
pause
