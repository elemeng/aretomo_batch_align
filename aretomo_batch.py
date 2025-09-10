#!/usr/bin/env python3
"""
aretomo_batch.py  —— 通用 CLI：递归找 *.st+*.rawtlt，并行对齐，输出 Warp 格式
用法：
    python aretomo_batch.py imod_root/ out_root -j 2 -g 0,1 --align-z 400 --tilt-axis 0.0 1
"""

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    sys.exit("pip install tqdm")


# ---------- 参数 ----------
def parse_args():
    p = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("imod_dir", help="根目录，会递归查找 *.st + *.rawtlt")
    p.add_argument("out_dir", help="结果根目录")
    p.add_argument("-j", "--jobs", type=int, default=2, help="并行任务数")
    p.add_argument("-g", "--gpus", default="0,1", help="GPU 列表，逗号分隔")
    p.add_argument("--aretomo", default="AreTomo2", help="可执行文件路径")
    p.add_argument("--max-retries", type=int, default=2)
    p.add_argument("--vol-z", default="0")
    p.add_argument("--align-z", default="1200", help="-AlignZ Default: 1200")
    p.add_argument(
        "--tilt-axis",
        help="可选 -TiltAxis",
    )
    p.add_argument("--dark-tol", type=float, default=0.7)
    p.add_argument(
        "--show-output", action="store_true", help="仅第一个任务实时输出到终端"
    )
    return p.parse_args()


# ---------- 找数据 ----------
def find_tilt_series(root: Path):
    pairs = []
    for st in root.rglob("*.st"):
        tlt = st.with_suffix(".rawtlt")
        if tlt.exists():
            pairs.append((st, tlt))
    if not pairs:
        sys.exit("未找到任何 *.st + *.rawtlt 对")
    return sorted(pairs)


# ---------- 单任务 ----------
def run_one(st: Path, tlt: Path, out_stem: Path, gpu: int, args, show_log: bool):
    log_dir = out_stem.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{st.stem}.log"

    cmd = [
        args.aretomo,
        "-InMrc",
        str(st),
        "-OutMrc",
        str(out_stem),
        "-AngFile",
        str(tlt),
        "-VolZ",
        args.vol_z,
        "-Align",
        "1",
        "-TiltCor",
        "0",
        "-DarkTol",
        str(args.dark_tol),
        "-OutImod",
        "2",
        "-Gpu",
        str(gpu),
    ]
    if args.align_z is not None:
        cmd += ["-AlignZ", str(args.align_z)]
    if args.tilt_axis is not None:
        cmd += ["-TiltAxis", str(args.tilt_axis[0]), str(args.tilt_axis[1])]

    for try_i in range(args.max_retries + 1):
        if try_i:
            print(f"重试 {try_i}/{args.max_retries} ：{st.stem}")
        with log.open("w") as fh:
            fh.write(" ".join(cmd) + "\n")
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in proc.stdout:
                fh.write(line)
                fh.flush()
                if show_log:
                    print(line, end="")
            proc.wait()
            if (
                proc.returncode == 0
                and (out_stem.parent / f"{out_stem.name}_Imod").exists()
            ):
                return True, str(log)
    return False, str(log)


# ---------- 主流程 ----------
def main():
    args = parse_args()
    if not shutil.which(args.aretomo):
        sys.exit(f"AreTomo2 不在 PATH：{args.aretomo}")
    imod = Path(args.imod_dir).resolve()
    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    gpus = list(map(int, args.gpus.split(",")))

    pairs = find_tilt_series(imod)
    tasks = [
        (
            st,
            tlt,
            out / st.parent.relative_to(imod) / st.stem,
            gpus[i % len(gpus)],
            args,
            args.show_output and i == 0,
        )
        for i, (st, tlt) in enumerate(pairs)
    ]

    ok, ng = [], []
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        futs = {ex.submit(run_one, *t): t[0].stem for t in tasks}
        for fut in tqdm(as_completed(futs), total=len(futs), desc="Align"):
            name = futs[fut]
            success, log = fut.result()
            (ok if success else ng).append((name, log))

    print(f"\n完成：{len(ok)} | 失败：{len(ng)}")
    if ng:
        print("失败列表：")
        for n, l in ng:
            print(f"  {n}  -> {l}")

    # 保存汇总
    summary = {
        "total": len(tasks),
        "success": len(ok),
        "failed": [{"name": n, "log": l} for n, l in ng],
        "cmd_args": vars(args),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (out / "processing_summary.json").write_text(json.dumps(summary, indent=2))
    print("\n汇总已写入 processing_summary.json")


if __name__ == "__main__":
    import shutil

    main()
