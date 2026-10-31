# Windows 用ランチャー: 必要なライブラリを入れて設定画面 (bench.py) を開く
#   .\run_windows.ps1           設定画面から計測
#   .\run_windows.ps1 --yes     既定値でそのまま計測
#   python plot.py              グラフだけ作り直す
Set-Location $PSScriptRoot
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Write-Host "Python 3.9 以上をインストールしてください"; exit 1 }
if (-not ((Get-Command clang -ErrorAction SilentlyContinue) -or (Get-Command gcc -ErrorAction SilentlyContinue))) {
  Write-Host "C コンパイラ (clang または gcc) が必要です。例: scoop install llvm  /  winget install LLVM.LLVM"; exit 1
}
python -m pip install -q -r requirements.txt
if ($LASTEXITCODE -ne 0) { python -m pip install -q numpy matplotlib }
python bench.py @args
