# このPCの作業用Python、またはリポジトリ内の仮想環境で検証室を起動する。
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$labPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $labPython)) {
    $labPython = Join-Path $PSScriptRoot '..\..\work\solver-venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $labPython)) {
    throw 'solver/README.md の環境構築手順を実行してください。'
}
Write-Host '公休表 検証室: http://127.0.0.1:8765/'
Write-Host '終了するには Ctrl+C を押してください。'
& $labPython -m solver.server
