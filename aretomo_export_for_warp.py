#!/usr/bin/env python3
"""
cleanup_aretomo.py
~~~~~~~~~~~~~~~~~~

Cleanup and reorganize AreTomo2 alignment outputs into a Warp-friendly structure.

Typical AreTomo2 outputs contain a mixture of:
  - *_Imod/ directories with IMOD command and alignment files
  - raw .aln and .mrc files in the alignment root
  - logs scattered across subdirectories

This script:
  1. Removes unnecessary *_st.mrc files inside *_Imod/.
  2. Renames and moves Warp-required files from *_Imod/ into aretomo_align/imod/<stem>/.
  3. Moves .aln and .mrc into aretomo_align/<stem>/.
  4. Moves logs into aretomo_align/<stem>/logs/.
  5. Writes a cleanup_summary.json recording all actions (moved, deleted, processed).

Example:
    python cleanup_aretomo.py aretomo_align/

After running, you will have:
  aretomo_align/
    ├── Position_01/
    │    ├── Position_01.aln
    │    ├── Position_01.mrc
    │    └── logs/
    ├── Position_02/
    │    ├── Position_02.aln
    │    ├── Position_02.mrc
    │    └── logs/
    └── imod/
         ├── Position_01/
         │    ├── Position_01.tlt
         │    ├── Position_01.xf
         │    └── ...
         └── Position_02/
              ├── Position_02.tlt
              ├── Position_02.xf
              └── ...
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Clean and reorganize AreTomo2 outputs into a Warp-friendly structure.\n\n"
            "Input:  Root directory (e.g. aretomo_align/) containing *_Imod/ dirs, .aln, .mrc, logs.\n"
            "Output: Reorganized structure with per-series folders and an 'imod/' subfolder.\n"
            "Also generates cleanup_summary.json logging all operations."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "root",
        help=(
            "Root directory of AreTomo2 outputs (e.g. aretomo_align/).\n"
            "The script will process all *_Imod/ directories and related files inside this root."
        ),
    )
    return parser.parse_args()


def main():
    args = parse_args()
    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        sys.exit(f"Directory not found: {root}")

    imod_root = root / "imod"
    imod_root.mkdir(exist_ok=True)

    summary = {
        "processed": [],
        "deleted": [],
        "moved": [],
        "imod_dirs": [],
    }

    # ---------- Process *_Imod directories ----------
    for imod_dir in root.glob("**/*_Imod"):
        if not imod_dir.is_dir():
            continue

        stem = imod_dir.name.replace("_Imod", "")  # e.g. Position_16
        tgt_dir = imod_root / stem
        tgt_dir.mkdir(exist_ok=True)
        summary["imod_dirs"].append(str(imod_dir))

        # File rename rules
        rename_map = {
            "newst.com": f"{stem}_newst.com",
            "tilt.com": f"{stem}_tilt.com",
            f"{stem}_st_order_list.csv": f"{stem}_order_list.csv",
            f"{stem}_st.tlt": f"{stem}.tlt",
            f"{stem}_st.xf": f"{stem}.xf",
            f"{stem}_st.xtilt": f"{stem}.xtilt",
        }

        for src in imod_dir.iterdir():
            # Remove *_st.mrc
            if src.suffix == ".mrc" and "_st" in src.stem:
                try:
                    src.unlink()
                    summary["deleted"].append(str(src))
                except Exception as e:
                    print(f"Failed to delete {src}: {e}")
                continue

            # Rename and move
            new_name = rename_map.get(src.name, src.name)
            dst = tgt_dir / new_name
            shutil.move(str(src), str(dst))
            summary["moved"].append({"src": str(src), "dst": str(dst)})

        # Remove empty _Imod directory
        try:
            imod_dir.rmdir()
            summary["deleted"].append(str(imod_dir))
        except OSError:
            pass

    # ---------- Collect .aln files ----------
    for aln in root.rglob("*.aln"):
        stem = aln.stem.replace(".st", "")  # Position_16.st.aln → Position_16
        pos_dir = root / stem
        pos_dir.mkdir(exist_ok=True)
        dst = pos_dir / aln.name
        shutil.move(str(aln), str(dst))
        summary["moved"].append({"src": str(aln), "dst": str(dst)})

    # ---------- Collect .mrc files ----------
    for mrc in root.rglob("*.mrc"):
        if mrc.is_relative_to(imod_root):
            continue  # skip files already in imod/
        stem = mrc.stem
        pos_dir = root / stem
        pos_dir.mkdir(exist_ok=True)
        dst = pos_dir / mrc.name
        shutil.move(str(mrc), str(dst))
        summary["moved"].append({"src": str(mrc), "dst": str(dst)})

    # ---------- Move logs ----------
    for log_dir in root.rglob("logs"):
        if not log_dir.is_dir():
            continue
        stem = log_dir.parent.name
        pos_dir = root / stem
        pos_dir.mkdir(exist_ok=True)
        tgt_logs = pos_dir / "logs"
        if log_dir != tgt_logs:
            shutil.move(str(log_dir), str(tgt_logs))
            summary["moved"].append({"src": str(log_dir), "dst": str(tgt_logs)})

    # ---------- Write summary ----------
    summary["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")  # type: ignore
    summary_file = root / "cleanup_summary.json"
    summary_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Cleanup finished! Summary written to {summary_file}")


if __name__ == "__main__":
    main()
