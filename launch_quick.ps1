# ワンクリック: 8501 が空なら Streamlit を裏で起動 → ブラウザで開く
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$port = 8501
$streamlit = Join-Path $root ".venv\Scripts\streamlit.exe"
if (-not (Test-Path $streamlit)) {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
        "仮想環境が見つかりません。先に install.bat を実行してください。`n$streamlit",
        "メルカリ紹介文",
        "OK",
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
}

$listening = $false
try {
    $listening = [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
} catch {
    $listening = $false
}

if (-not $listening) {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $streamlit
    $psi.Arguments = "run app.py --server.port $port --server.headless true --browser.gatherUsageStats false"
    $psi.WorkingDirectory = $root
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    [void][System.Diagnostics.Process]::Start($psi)
    Start-Sleep -Seconds 4
}

Start-Process "http://localhost:$port/"
