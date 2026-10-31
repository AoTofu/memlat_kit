"""plot.py - results/ 以下の CSV を読み、元画像風のグラフを作る (Windows / macOS 共通)
usage: python plot.py
  -> results/cpu_latency.png      (実測のみ)
     results/cpu_latency_ref.png  (実測 + 元画像の 388H / M6)
     results/gpu_latency.png
"""
import os, glob, json, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib import font_manager
from refdata import REF_PX

HERE = os.path.dirname(os.path.abspath(__file__)); RES = os.path.join(HERE, "results")
have = {f.name for f in font_manager.fontManager.ttflist}
plt.rcParams["font.family"] = [f for f in ["Hiragino Sans", "Hiragino Kaku Gothic ProN", "Yu Gothic", "Meiryo",
                                           "Noto Sans CJK JP", "Noto Sans JP"] if f in have] + ["sans-serif"]
STROKE = [pe.withStroke(linewidth=3, foreground="#000a")]
hx = lambda s: [int(s[i:i + 2], 16) / 255 for i in (1, 3, 5)]


def load(path):
    meta, xs, ys = {}, [], []
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if line.startswith("#"):
            if ":" in line:
                k, v = line[1:].split(":", 1); meta[k.strip()] = v.strip()
        elif line and line[0].isdigit():
            a, b = line.split(","); xs.append(float(a)); ys.append(float(b))
    return meta, np.array(xs), np.array(ys)


def machine(d):
    p = os.path.join(RES, d, "machine.json")
    if not os.path.exists(p): return {}
    try: return json.load(open(p, encoding="utf-8-sig"))
    except Exception: return {}


def ref_series():
    COL = {"388H-LPE": "#5b5bff", "388H-E": "#4aa3ff", "388H-P": "#3ff0dc",
           "M6-E": "#ff7a3d", "M6-S": "#c9f03f", "M6-P": "#ffad45"}
    out = []
    for k, pts in REF_PX.items():
        o = np.array([4 + (p - 132) / 132.7 for p, _ in pts]); y = np.array([v for _, v in pts])
        oo = np.linspace(o[0], o[-1], 600); yy = np.interp(oo, o, y)
        yy = np.convolve(np.pad(yy, 4, mode="edge"), np.ones(9) / 9, "valid"); yy[-1] = y[-1]
        out.append(dict(name=k, x=2 ** oo, y=yy, color=COL[k], end=y[-1], ref=True))
    return out


# ---------------- 描画の共通部品 ----------------
def new_fig(title, subtitle):
    fig = plt.figure(figsize=(20, 11.25), dpi=110)
    H, W = 450, 800; yy, xx = np.mgrid[0:H, 0:W]
    r = np.sqrt(((xx - W * 0.45) / W) ** 2 + ((yy - H * 0.62) / H * 0.7) ** 2)
    t = np.clip(1 - r / 0.6, 0, 1) ** 1.6
    base = np.array([0.02, 0.02, 0.04]); glow = np.array([0.25, 0.17, 0.45])
    fb = fig.add_axes([0, 0, 1, 1]); fb.imshow(base + (glow - base) * t[..., None], aspect="auto", extent=(0, 1, 0, 1)); fb.axis("off")
    ax = fig.add_axes([0.06, 0.12, 0.86, 0.61]); ax.set_facecolor((0, 0, 0, 0))
    fig.text(0.5, 0.9, title, color="white", fontsize=48, weight="bold", ha="center")
    fig.text(0.5, 0.835, subtitle, color="#b8b6c8", fontsize=22, ha="center")
    fig.text(0.035, 0.80, "レイテンシ\n(ns)", color="white", fontsize=18, ha="center", weight="bold")
    fig.text(0.955, 0.095, "サイズ\n(KB)", color="white", fontsize=16, ha="center", weight="bold")
    return fig, ax


def style_axes(ax, xmax, ymax, ystep):
    ax.set_xscale("log", base=2)
    ticks = [4 * 2 ** i for i in range(22) if 4 * 2 ** i <= xmax * 1.01]
    ax.set_xticks(ticks); ax.set_xticklabels([str(t) for t in ticks]); ax.minorticks_off()
    ax.set_xlim(4, xmax * 3.2); ax.set_ylim(0, ymax); ax.set_yticks(range(0, int(ymax) + 1, ystep))
    ax.tick_params(colors="#9a98aa", labelsize=17, length=0, pad=10)
    for lab in ax.get_xticklabels(): lab.set_fontsize(12)
    ax.grid(axis="y", color="#ffffff", alpha=.25, ls=(0, (8, 6)), lw=1)
    for s in ax.spines.values(): s.set_visible(False)
    ax.axhline(0, color="#ffffff", alpha=.6, lw=1)


def draw_series(ax, series, label_x, gap):
    for s in series:
        ref = s.get("ref")
        if not ref: ax.plot(s["x"], s["y"], color=s["color"], lw=9, alpha=0.12, solid_capstyle="round")
        ax.plot(s["x"], s["y"], color=s["color"], lw=1.8 if ref else 2.8, alpha=.55 if ref else 1, solid_capstyle="round")
    ends = sorted(series, key=lambda s: -s["end"]); pos = []
    for s in ends:
        p = s["end"]
        if pos and pos[-1] - p < gap: p = pos[-1] - gap
        pos.append(p)
    for s, p in zip(ends, pos):
        c, a, ref = s["color"], (.6 if s.get("ref") else 1), s.get("ref")
        ax.text(label_x, p, f"{s['end']:.0f}ns", color=c, alpha=a, fontsize=22 if ref else 28,
                weight="bold", ha="right", va="center", path_effects=STROKE)
        ax.plot([label_x * 1.2, s["x"][-1]], [s["end"]] * 2, color=c, ls=(0, (6, 5)), lw=1.6, alpha=.6 * a)
        ax.text(s["x"][-1] * 1.08, s["end"], s["name"], color=c, alpha=a, fontsize=14, weight="bold",
                va="center", path_effects=STROKE)


def render_badges(fig, badges):
    """角丸グラデーションのバッジ。ピクセル単位で生成して貼るので形が揃い、縁にバリが出ない"""
    fig.canvas.draw(); R = fig.canvas.get_renderer(); FW, FH = fig.bbox.width, fig.bbox.height
    y = 0.655
    for text, c1, c2, sub in badges:
        hp = int(round(0.045 * FH)); padx = int(hp * 0.32); rad = int(hp * 0.22)
        t = fig.text(0, 0, text, fontsize=26, weight="bold"); tw = t.get_window_extent(R).width; t.remove()
        wp = int(round(tw + 2 * padx)); xo = int(round(0.085 * FW)); yo = int(round(y * FH))
        ss = 4; yy, xx = np.mgrid[0:hp * ss, 0:wp * ss]; xx = (xx + .5) / ss; yy = (yy + .5) / ss
        dx = np.maximum(np.maximum(rad - xx, xx - (wp - rad)), 0)
        dy = np.maximum(np.maximum(rad - yy, yy - (hp - rad)), 0)
        m = (dx ** 2 + dy ** 2 <= rad ** 2).astype(float).reshape(hp, ss, wp, ss).mean((1, 3))
        g = np.linspace(0, 1, wp)[None, :, None]
        rgb = np.repeat(np.array(hx(c1)) * (1 - g) + np.array(hx(c2)) * g, hp, 0)
        fig.figimage(np.dstack([rgb, m]), xo=xo, yo=yo, origin="lower", zorder=5)
        fig.text((xo + padx) / FW, (yo + hp / 2) / FH, text, fontsize=26, weight="bold", color="#0a0a20", va="center", zorder=6)
        fig.text((xo + wp) / FW + 0.01, (yo + hp / 2) / FH, sub, fontsize=16, color="#9a98aa", va="center")
        y -= 0.06


def tail_value(y, n=8):
    return float(np.median(y[-n:]))


# ---------------- データ収集 ----------------
CPU_COL = {"windows": ["#ff4fb0", "#d27bff"], "mac": ["#ffc640", "#38c8ff", "#7dffb0"]}
BADGE_COL = {"windows": ("#ff3fa0", "#b07bff"), "mac": ("#38c8ff", "#ffc640")}
GPU_COL = {"windows": ("#5dff9a", "#2fd06a", "#a8ff5d"), "mac": ("#38c8ff", "#38c8ff", "#e8f4ff")}


def machine_dirs():
    return [d for d in sorted(os.listdir(RES)) if os.path.isdir(os.path.join(RES, d))] if os.path.isdir(RES) else []


def cpu_series():
    ser, badges, notes = [], [], []
    for d in machine_dirs():
        files = sorted(glob.glob(os.path.join(RES, d, "cpu_*.csv")))
        if not files: continue
        mi = machine(d); kind = "mac" if d.startswith("mac") else "windows"; short = mi.get("short", d)
        plotted = 0
        for f in files:
            meta, x, y = load(f)
            if len(x) < 4: continue
            if kind == "windows" and plotted >= 1 and not mi.get("plot_all_cores"): continue
            tag = os.path.basename(f)[4:-4]
            ser.append(dict(name=f"{short}-{tag}", x=x, y=y, color=CPU_COL[kind][plotted % 3], end=tail_value(y)))
            notes.append(f"{short}-{tag}: {meta.get('ghz_start', '?')}GHz・ページ{int(meta.get('page_size', '0')) // 1024}KB")
            plotted += 1
        c1, c2 = BADGE_COL[kind]
        badges.append((mi.get("cpu", short), c1, c2, mi.get("memory", "")))
    return ser, badges, notes


def gpu_series():
    ser, badges, notes = [], [], []
    for d in machine_dirs():
        kind = "mac" if d.startswith("mac") else "windows"
        files = sorted(glob.glob(os.path.join(RES, d, "gpu*.csv")))
        if os.path.join(RES, d, "gpu_locked.csv") in files:  # 固定クロックの結果があればそれを使う
            files = [os.path.join(RES, d, "gpu_locked.csv")]
        for f in files:
            meta, x, y = load(f)
            if len(x) < 4: continue
            name = meta.get("gpu", d).replace("NVIDIA ", "").replace("GeForce ", "")
            line, c1, c2 = GPU_COL[kind]
            ser.append(dict(name=name, x=x, y=y, color=line, end=tail_value(y)))
            badges.append((name, c1, c2, meta.get("note", "")))
            notes.append(f"{name}: {meta.get('platform', '')}")
    return ser, badges, notes


# ---------------- 出力 ----------------
def cpu_chart(with_ref):
    ser, badges, notes = cpu_series()
    if not ser: return None
    if with_ref:
        ser = ser + ref_series()
        badges += [("Ultra X9 388H", "#3a5bff", "#3ff0dc", "LPDDR5X 9600（元画像から読取）"),
                   ("M6", "#ff6a3d", "#e8f040", "LPDDR5X 10667（元画像から読取）")]
    fig, ax = new_fig("メモリとキャッシュのレイテンシ", "ランダムアクセス（1スレッド・ポインタチェイス）　低いほど良い")
    ymax = max(125, int(np.ceil(max(s["end"] for s in ser) / 25 + 0.6)) * 25)
    style_axes(ax, max(s["x"][-1] for s in ser), ymax, 25)
    draw_series(ax, ser, 2600, ymax * 0.052)
    render_badges(fig, badges)
    foot = "※ 全機種同一の memlat.c（32bit インデックス・64B 間隔・同一乱数列・40ms×5 回の中央値）。 " + " / ".join(notes)
    if with_ref: foot += "\n※ 388H / M6 は元画像の曲線を目視で読み取った近似値（128MB まで。計測方法は不明なので参考扱い）。"
    fig.text(0.06, 0.012, foot, color="#77758a", fontsize=11)
    out = os.path.join(RES, "cpu_latency_ref.png" if with_ref else "cpu_latency.png")
    fig.savefig(out); plt.close(fig); print("wrote", out); return out


def gpu_chart():
    ser, badges, notes = gpu_series()
    if not ser: return None
    fig, ax = new_fig("GPU メモリとキャッシュのレイテンシ", "ランダムアクセス（1ワークアイテム・ポインタチェイス / OpenCL）　低いほど良い")
    ymax = int(np.ceil(max(float(np.max(s["y"])) for s in ser) / 40 + 0.5)) * 40
    style_axes(ax, max(s["x"][-1] for s in ser), ymax, 40)
    draw_series(ax, ser, 2600, ymax * 0.05)
    render_badges(fig, badges)
    fig.text(0.06, 0.012, "※ 全機種同一の gpulat.py（OpenCL・32bit インデックス・64B 間隔・同一乱数列・5 回の中央値をさらに複数パスで中央値）。 "
             + " / ".join(notes), color="#77758a", fontsize=11)
    out = os.path.join(RES, "gpu_latency.png"); fig.savefig(out); plt.close(fig); print("wrote", out); return out


def make_all(with_ref=True):
    """全グラフを作成して、作ったファイルのパスを返す"""
    outs = [cpu_chart(True) if with_ref else None, cpu_chart(False), gpu_chart()]
    return [o for o in outs if o]


if __name__ == "__main__":
    import sys
    make_all(with_ref="--no-ref" not in sys.argv)
