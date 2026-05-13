@echo off
chcp 65001 > nul
cd /d "%~dp0"

REM 仮想環境のPythonを直接使用（Activate.ps1不要）
if "%~1"=="" (
    echo 使い方: run.bat 画像1.jpg [画像2.jpg] ...
    echo 例: run.bat images\item1.jpg
    "%~dp0.venv\Scripts\python.exe" mercari_listing_generator.py
) else (
    "%~dp0.venv\Scripts\python.exe" mercari_listing_generator.py %*
)
