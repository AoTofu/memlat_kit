"""bench.py - 設定画面つきの計測ランチャー (Windows / macOS 共通)

  python bench.py          設定画面を表示 → 計測 → グラフ
  python bench.py --yes    設定画面を出さず既定値で実行

既定値は、作者の環境 (Ryzen 7 9850X3D + RTX 5080) で計測したときと同じ条件。
"""
import os, sys, json, shutil, platform, subprocess, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
IS_WIN, IS_MAC = sys.platform == "win32", sys.platform == "darwin"
os.chdir(HERE)


# ------------------------------------------------------------ マシン情報
def sh(cmd):
    try: return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
    except Exception: return ""

def ps_json(cmd):
    out = sh(["powershell", "-NoProfile", "-Command", cmd + " | ConvertTo-Json -Compress"])
    try:
        v = json.loads(out); return v if isinstance(v, list) else [v]
    except Exception: return [{}]

def machine_info():
    if IS_WIN:
        import re
        cpu = ps_json("Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors")[0]
        mem = ps_json("Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity,ConfiguredClockSpeed,SMBIOSMemoryType")
        name = re.sub(r"^(AMD|Intel\(R\) Core\(TM\)|Intel\(R\))\s*", "", cpu.get("Name", "CPU").strip())
        name = re.sub(r"\s*\d+-Core Processor", "", name).strip()
        gb = round(sum(int(m.get("Capacity") or 0) for m in mem) / 2 ** 30)
        ddr = {26: "DDR4", 34: "DDR5", 35: "LPDDR5"}.get(int(mem[0].get("SMBIOSMemoryType") or 0), "RAM")
        short = name.split()[-1]
        return dict(cpu=name, short=short, memory=f"{ddr}-{mem[0].get('ConfiguredClockSpeed')} {gb}GB",
                    logical=int(cpu.get("NumberOfLogicalProcessors") or 1), physical=int(cpu.get("NumberOfCores") or 1),
                    dir=f"windows-{short}")
    if IS_MAC:
        chip = sh(["sysctl", "-n", "machdep.cpu.brand_string"]) or "Apple"
        short = chip.replace("Apple ", "")
        gb = int(sh(["sysctl", "-n", "hw.memsize"]) or 0) // 2 ** 30
        mtype = ""
        for line in sh(["system_profiler", "SPMemoryDataType"]).splitlines():
            if "Type:" in line: mtype = line.split(":", 1)[1].strip(); break
        npl = int(sh(["sysctl", "-n", "hw.nperflevels"]) or 1); levels = []
        for i in range(npl):
            g = lambda k: sh(["sysctl", "-n", f"hw.perflevel{i}.{k}"])
            levels.append(f"{g('name')} x{g('physicalcpu')} (L1D {int(g('l1dcachesize') or 0)//1024}KB, L2 {int(g('l2cachesize') or 0)//2**20}MB)")
        return dict(cpu=chip, short=short, memory=f"{mtype or 'Unified'} {gb}GB", perflevels=", ".join(levels), nperflevels=npl,
                    page_size=int(sh(["sysctl", "-n", "hw.pagesize"]) or 0), cachelinesize=int(sh(["sysctl", "-n", "hw.cachelinesize"]) or 0),
                    os=f"macOS {sh(['sw_vers', '-productVersion'])}", model=sh(["sysctl", "-n", "hw.model"]),
                    dir="mac-" + short.replace(" ", ""))
    return dict(cpu=platform.processor() or "CPU", short="cpu", memory="", dir="other")


# ------------------------------------------------------------ 設定
def defaults(mi):
    if IS_WIN:
        # 作者の環境: 論理CPU 0 と 14 (= 物理コア0と7)。他の PC では「先頭と最後の物理コア」
        cores = f"0,{max(0, mi['logical'] - (mi['logical'] // max(1, mi['physical'])))}"
    else:
        cores = "P,E"
    return dict(target="CPU + GPU", cores=cores, cpu_maxmb=1024, stride=64, cpu_ms=40, cpu_reps=5,
                gpu_maxmb=2048, gpu_passes=3, gpu_steps=300000,
                gpu_clock="両方 (固定なし + 固定)" if IS_WIN else "固定しない（macOS は固定不可）",
                ref="表示する", open_after="開く")

CHOICES = {
    "target": ["CPU + GPU", "CPU のみ", "GPU のみ"],
    "gpu_clock": ["両方 (固定なし + 固定)", "固定する（最大クロック）", "固定しない"] if IS_WIN else ["固定しない（macOS は固定不可）"],
    "ref": ["表示する", "表示しない"],
    "open_after": ["開く", "開かない"],
}
ITEMS = [  # key, ラベル, 説明
    ("target", "計測対象", ""),
    ("cores", "CPU コア", "論理CPU番号をカンマ区切り (例 0,14)" if IS_WIN else "P / E をカンマ区切り (QoS で指定)"),
    ("cpu_maxmb", "CPU 最大サイズ (MB)", "4KB からこのサイズまで"),
    ("stride", "ノード間隔 (B)", "64 推奨。128 にすると Apple のライン長に合わせた条件"),
    ("cpu_ms", "CPU 1回の計測時間 (ms)", ""),
    ("cpu_reps", "CPU 計測回数 (中央値)", ""),
    ("gpu_maxmb", "GPU 最大サイズ (MB)", "GPU のメモリ量に応じて自動で小さくなる"),
    ("gpu_passes", "GPU パス数 (中央値)", ""),
    ("gpu_steps", "GPU 1回のステップ数", ""),
    ("gpu_clock", "GPU クロック固定", "NVIDIA のみ。固定時は管理者権限 (UAC) が必要" if IS_WIN else ""),
    ("ref", "元画像の参考曲線", "388H / M6 を重ねたグラフも作る"),
    ("open_after", "終了後にグラフを", ""),
]

def show(s, d):
    print("\n\033[1;36m==== メモリレイテンシ計測  設定 ====\033[0m")
    for i, (k, label, help_) in enumerate(ITEMS, 1):
        mark = " " if s[k] == d[k] else "\033[1;33m*\033[0m"
        print(f" {i:>2}.{mark}{label:<20} : {s[k]}" + (f"   \033[90m{help_}\033[0m" if help_ else ""))
    print("\033[90m  * = 既定値から変更。既定値は作者の PC で計測したときと同じ条件です\033[0m")
    print("\n Enter: この設定で開始   番号: 変更   d: 既定値に戻す   q: 終了")

def edit(s, k):
    label = dict((a, b) for a, b, _ in ITEMS)[k]
    if k in CHOICES:
        opts = CHOICES[k]
        for i, o in enumerate(opts, 1): print(f"   {i}. {o}")
        v = input(f" {label} を選択 [1-{len(opts)}]: ").strip()
        if v.isdigit() and 1 <= int(v) <= len(opts): s[k] = opts[int(v) - 1]
    else:
        v = input(f" {label} の新しい値 (今: {s[k]}): ").strip()
        if not v: return
        if isinstance(s[k], int):
            if v.isdigit() and int(v) > 0: s[k] = int(v)
            else: print("  正の整数を入力してください")
        else:
            s[k] = v.replace(" ", "")

def menu(s, d):
    while True:
        show(s, d)
        try: c = input(" > ").strip().lower()
        except EOFError: return True
        if c == "": return True
        if c == "q": return False
        if c == "d": s.clear(); s.update(d); continue
        if c.isdigit() and 1 <= int(c) <= len(ITEMS): edit(s, ITEMS[int(c) - 1][0])


# ------------------------------------------------------------ 実行
def say(m): print(f"\n\033[1;36m== {m}\033[0m", flush=True)

def wrap(cmd):
    """macOS では計測中にスリープしないよう caffeinate を付ける"""
    return (["caffeinate", "-i"] + cmd) if IS_MAC and shutil.which("caffeinate") else cmd

def build():
    exe = os.path.join(HERE, "memlat.exe" if IS_WIN else "memlat")
    cc = shutil.which("clang") or shutil.which("gcc")
    if not cc: sys.exit("C コンパイラ (clang / gcc) が見つかりません")
    cmd = [cc, "-O2", "-o", exe, os.path.join(HERE, "memlat.c")] + (["-ladvapi32"] if IS_WIN else [])
    say("CPU プログラムをビルド: " + " ".join(cmd))
    subprocess.run(cmd, check=True)
    return exe

def run_cpu(s, mi, out):
    exe = build()
    for c in [c for c in s["cores"].split(",") if c]:
        if IS_WIN:
            per = max(1, mi["logical"] // max(1, mi["physical"]))
            tag = f"core{int(c) // per}"
        else:
            tag = c.upper()
        say(f"CPU {tag} を計測中 (最大 {s['cpu_maxmb']}MB)")
        with open(os.path.join(out, f"cpu_{tag}.csv"), "w", encoding="utf-8", newline="\n") as f:
            subprocess.run(wrap([exe, c, str(s["cpu_maxmb"]), str(s["stride"]), str(s["cpu_ms"]), str(s["cpu_reps"])]), stdout=f, check=True)
        with open(os.path.join(out, f"cpu_{tag}.csv"), encoding="utf-8") as f:
            print("   " + " / ".join(l.strip("# \n") for l in f if "ghz" in l))

def gpu_args(s, out, name, note):
    return ["gpulat.py", os.path.join(out, name), "--passes", str(s["gpu_passes"]), "--maxmb", str(s["gpu_maxmb"]),
            "--steps", str(s["gpu_steps"]), "--stride", str(s["stride"]), "--note", note]

def have_opencl():
    try:
        import pyopencl as cl
        return any(d.type & cl.device_type.GPU for p in cl.get_platforms() for d in p.get_devices())
    except Exception as e:
        print("   OpenCL が使えません:", e); return False

def run_gpu(s, out):
    if not have_opencl(): print("   GPU 計測をスキップします"); return
    mode = s["gpu_clock"]
    if not mode.startswith("固定する"):
        say("GPU を計測中 (クロック固定なし)")
        note = "クロック固定不可（macOS）" if IS_MAC else "クロック固定なし"
        subprocess.run(wrap([sys.executable, "-W", "ignore"] + gpu_args(s, out, "gpu.csv" if IS_MAC else "gpu_unlocked.csv", note)))
    if IS_WIN and (mode.startswith("両方") or mode.startswith("固定する")):
        if not shutil.which("nvidia-smi"): print("   nvidia-smi が無いためクロック固定は省略"); return
        say("GPU を計測中 (クロック固定)  → UAC の確認で「はい」を押してください")
        subprocess.run(elevated_cmd(s, out))

def elevated_cmd(s, out, runas=True):
    """管理者権限で bench.py --locked-worker を起動する PowerShell コマンド"""
    sj = json.dumps(s, ensure_ascii=True).replace('"', "'")  # 引数の中で " を使わない
    argl = " ".join(f'"{a}"' for a in [os.path.join(HERE, "bench.py"), "--locked-worker", sj, os.path.abspath(out)])
    q = lambda t: "'" + t.replace("'", "''") + "'"           # PowerShell の単一引用符文字列
    ps = (f"Start-Process -FilePath {q(sys.executable)} -ArgumentList {q(argl)} -Wait -WorkingDirectory {q(HERE)}"
          + (" -Verb RunAs" if runas else " -NoNewWindow"))
    return ["powershell", "-NoProfile", "-Command", ps]

def locked_worker(sjson, out):
    """管理者権限で動く部分: 最大クロックに固定 → 計測 → 必ず元に戻す"""
    s = json.loads(sjson.replace("'", '"'))
    line = sh(["nvidia-smi", "--query-supported-clocks=mem,gr", "--format=csv,noheader,nounits"]).splitlines()[0]
    m, g = [x.strip() for x in line.split(",")]
    try:
        r1 = subprocess.run(["nvidia-smi", "-lgc", f"{g},{g}"]).returncode
        r2 = subprocess.run(["nvidia-smi", "-lmc", f"{m},{m}"]).returncode
        if r1 or r2:  # 固定できなかった場合は「固定」と記録しない
            print("!! クロックを固定できませんでした（管理者権限が必要です）。固定版の計測を中止します")
            input("Enter で閉じる"); return
        subprocess.run([sys.executable, "-W", "ignore"] + gpu_args(s, out, "gpu_locked.csv", f"コア{g} / メモリ{m}MHz 固定"))
    finally:
        subprocess.run(["nvidia-smi", "-rgc"]); subprocess.run(["nvidia-smi", "-rmc"])

def open_files(paths):
    for p in paths:
        if not os.path.exists(p): continue
        if IS_WIN: os.startfile(p)
        elif IS_MAC: subprocess.run(["open", p])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="設定画面を出さずに既定値で実行")
    ap.add_argument("--locked-worker", nargs=2, help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.locked_worker: locked_worker(*a.locked_worker); return

    if IS_WIN: os.system("")  # Windows コンソールで色付き表示を有効化
    mi = machine_info()
    print(f"\n 機種: {mi['cpu']}  /  {mi['memory']}" + (f"\n コア構成: {mi['perflevels']}" if mi.get("perflevels") else ""))
    if IS_MAC and mi.get("nperflevels", 1) >= 3:
        print("\033[1;33m !! コアが 3 種類あります。QoS で指定できるのは最速 (P) と最省電力 (E) のみです\033[0m")
    d = defaults(mi); s = dict(d)
    if not a.yes and not menu(s, d): return

    out = os.path.join("results", mi["dir"]); os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "machine.json"), "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in mi.items() if k != "dir"} | {"settings": s}, f, ensure_ascii=False, indent=1)
    if s["target"] != "GPU のみ": run_cpu(s, mi, out)
    if s["target"] != "CPU のみ": run_gpu(s, out)

    say("グラフを作成")
    import plot
    made = plot.make_all(with_ref=s["ref"] == "表示する")
    if IS_MAC:
        z = shutil.make_archive(mi["dir"], "zip", "results", mi["dir"]); print("   計測データ:", z)
    say("完了")
    if s["open_after"] == "開く": open_files(made)


if __name__ == "__main__":
    main()
