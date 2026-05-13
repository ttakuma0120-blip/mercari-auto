@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo パッケージをインストールしています...
"%~dp0.venv\Scripts\python.exe" -m pip install -r requirements.txt
echo.
echo 完了しました。run.bat でツールを実行できます。
pause
