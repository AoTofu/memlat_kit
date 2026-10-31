#!/bin/bash
# Apple Silicon Mac 用ランチャー: 環境を準備して設定画面 (bench.py) を開く
#   bash run_mac.sh          設定画面から計測
#   bash run_mac.sh --yes    既定値でそのまま計測
set -uo pipefail
cd "$(dirname "$0")"
warn() { printf "\033[1;33m!! %s\033[0m\n" "$*"; }

[ "$(uname -s)" = "Darwin" ] || { echo "macOS 専用です (Windows は run_windows.ps1)"; exit 1; }
[ "$(uname -m)" = "arm64" ] || warn "arm64 ではありません ($(uname -m))。Rosetta 経由だと正しく測れません"
if ! xcode-select -p >/dev/null 2>&1; then
  warn "Xcode Command Line Tools が必要です。インストール画面を開きます。完了後にもう一度 bash run_mac.sh を実行してください"
  xcode-select --install; exit 1
fi
pmset -g batt | head -1 | grep -q "AC Power" || warn "電源アダプタにつないでください（バッテリー駆動だとクロックが下がることがあります）"
[ "$(pmset -g | awk '/lowpowermode/{print $2}')" = "1" ] && warn "低電力モードが ON です。OFF にしてから実行してください"
warn "計測中はほかのアプリを閉じて、Mac を操作しないでください"

# Python (3.9 以上) と仮想環境
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v $c >/dev/null && $c -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then PY=$c; break; fi
done
[ -n "$PY" ] || { warn "python3 が見つかりません"; exit 1; }
[ -d .venv ] || $PY -m venv .venv
source .venv/bin/activate
python -m pip install -q --upgrade pip
python -m pip install -q numpy matplotlib || { warn "numpy / matplotlib のインストールに失敗しました"; exit 1; }
python -m pip install -q pyopencl || warn "pyopencl のインストールに失敗しました（GPU 計測はスキップされます）"

python bench.py "$@"
