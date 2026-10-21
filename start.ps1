# 先在使用者選擇的 conda / venv 環境啟動本程式。
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
python -m streamlit run app.py
