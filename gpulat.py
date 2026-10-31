"""gpulat.py - GPU memory/cache latency (OpenCL, 1 work-item random pointer chase)
Windows (NVIDIA/AMD/Intel) と macOS (Apple GPU, OpenCL 1.2) で同一カーネル・同一乱数列。
 - 32bit インデックスを辿る / ノード間隔 64B (--stride) / 単一巡回ランダム順列 (seed=1)
 - 各サイズ: ウォームアップ後、30万ステップ (--steps) x5 回の中央値。前回の終点から続けて辿る
 - パス数 (--passes, 既定3) の中央値を出力
usage: python gpulat.py out.csv [--passes 3] [--maxmb 2048] [--steps 300000] [--stride 64] [--note TEXT]
"""
import sys, argparse, platform
import numpy as np, pyopencl as cl

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("--passes", type=int, default=3)
ap.add_argument("--maxmb", type=int, default=2048)
ap.add_argument("--steps", type=int, default=300_000)
ap.add_argument("--stride", type=int, default=64)
ap.add_argument("--note", default="")
args = ap.parse_args()

dev = None
for p in cl.get_platforms():
    for d in p.get_devices():
        if d.type & cl.device_type.GPU: dev = d; break
    if dev: break
if dev is None: sys.exit("OpenCL GPU device not found")
ctx = cl.Context([dev])
q = cl.CommandQueue(ctx, properties=cl.command_queue_properties.PROFILING_ENABLE)
prg = cl.Program(ctx, """
__kernel void chase(__global const uint* restrict a, uint start, uint n, __global uint* out){
  uint p = start; for (uint i = 0; i < n; i++) p = a[p]; out[0] = p; }""").build()
K = cl.Kernel(prg, "chase")
STRIDE = max(2, args.stride // 4)  # uint32 単位 (64B なら 16)
NODE = STRIDE * 4                   # バイト
MAX = min(args.maxmb << 20, dev.max_mem_alloc_size, dev.global_mem_size // 4)
MAX = 1 << (MAX.bit_length() - 1)   # 2 のべき乗に丸める
buf = cl.Buffer(ctx, cl.mem_flags.READ_ONLY, MAX)
out = cl.Buffer(ctx, cl.mem_flags.WRITE_ONLY, 4)
res = np.zeros(1, np.uint32)


def run(start, n):
    K.set_args(buf, np.uint32(start), np.uint32(n), out)
    e = cl.enqueue_nd_range_kernel(q, K, (1,), (1,)); e.wait()
    cl.enqueue_copy(q, res, out).wait()
    return e.profile.end - e.profile.start, int(res[0])


sizes = []
k = 0
while True:
    kb = 4 * 2 ** (k / 8); k += 1
    if kb * 1024 > MAX * 1.0001: break
    sizes.append(kb)

allp = []
for pas in range(args.passes):
    rng = np.random.default_rng(1)
    vals = []
    for kb in sizes:
        lines = max(2, int(kb * 1024 / NODE))
        perm = rng.permutation(lines).astype(np.uint32)
        host = np.zeros(lines * STRIDE, np.uint32)
        host[perm * STRIDE] = np.roll(perm, -1) * STRIDE
        cl.enqueue_copy(q, buf, host).wait()
        _, p = run(int(perm[0]) * STRIDE, min(lines * 2, 2_000_000))
        N = args.steps; ts = []
        for _ in range(5):
            t, p = run(p, N); ts.append(t / N)
        vals.append(float(np.median(ts)))
        print(f"\r pass {pas+1}/{args.passes}  {kb:>10.0f} KB  {vals[-1]:7.1f} ns ", end="", file=sys.stderr, flush=True)
    allp.append(vals)
print(file=sys.stderr)
med = np.median(np.array(allp), axis=0)
with open(args.out, "w", encoding="utf-8", newline="\n") as f:
    f.write(f"# gpu: {dev.name}\n# platform: {dev.platform.name} / {dev.version}\n# os: {platform.platform()}\n")
    f.write(f"# max_buffer_mb: {MAX >> 20}\n# passes: {args.passes}\n# steps: {args.steps}\n# stride: {NODE}\n# note: {args.note}\n")
    f.write("kb,ns\n")
    for kb, v in zip(sizes, med): f.write(f"{kb:.2f},{v:.3f}\n")
print("wrote", args.out)
