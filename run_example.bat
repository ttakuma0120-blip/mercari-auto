@echo off
chcp 65001 > nul
echo メルカリ商品紹介文生成ツール
echo.
echo 使い方: run_example.bat 画像1.jpg 画像2.jpg ...
echo.
if "%~1"=="" (
    echo 画像ファイルを指定してください。
    echo 例: run_example.bat images\item1.jpg images\item2.jpg
    exit /b 1
)
python mercari_listing_generator.py %*
