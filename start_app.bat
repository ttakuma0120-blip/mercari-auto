@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo メルカリ商品紹介文生成 - Webアプリを起動しています...
echo ブラウザが自動で開きます。開かない場合は http://localhost:8501 にアクセスしてください。
echo 終了するにはこのウィンドウを閉じてください。
echo.

"%~dp0.venv\Scripts\streamlit.exe" run app.py

pause
