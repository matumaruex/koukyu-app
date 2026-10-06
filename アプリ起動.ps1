# 公開版と同じスマホ画面と計算を、このPCだけで動かす。Vercelの無料枠は使わない。
# 初回だけ、Pythonの仮想環境（.venv）と計算ライブラリ（OR-Tools）を準備する。検証室（起動.ps1）と同じ .venv を使う。
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Host '初回の準備をしています（数分かかります）...'
    if (Get-Command py -ErrorAction SilentlyContinue) { py -m venv .venv } else { python -m venv .venv }
    if (-not (Test-Path -LiteralPath $python)) { throw 'Pythonが見つかりません。python.org から Python 3.12 を入れてから、もう一度実行してください。' }
    & $python -m pip install -r solver\requirements.txt
}
$url = 'http://127.0.0.1:8766/'
Write-Host "公休表（このPC版）: $url"
Write-Host 'データは公開版とは別に、このPCのブラウザに保存されます（設定 > データを書き出す/読み込む で移せます）。'
Write-Host '終了するには、このウィンドウで Ctrl+C を押してください。'
Start-Job -ScriptBlock { param($u) Start-Sleep -Seconds 2; Start-Process $u } -ArgumentList $url | Out-Null
& $python -m solver.app_server
