@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo 写真監視 → 自動出品ツールを起動しています...
echo images\inbox\ にサブフォルダを作って写真を入れると自動処理されます。
echo 終了するにはこのウィンドウで Ctrl+C を押してください。
echo.

"%~dp0.venv\Scripts\python.exe" photo_watcher.py

pause
