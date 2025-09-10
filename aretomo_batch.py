#!/usr/bin/env python3
"""
aretomo_batch.py - Batch AreTomo2 alignment tool
Recursively finds *.st + *.rawtlt pairs, supports parallel processing, and outputs Warp format.

Usage:
    python aretomo_batch.py imod_root/ out_root -j 2 -g 0,1 --align-z 400 --tilt-axis 0.0 1
"""

import argparse
import json
import logging
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple, Dict, Any

try:
    from tqdm import tqdm
except ImportError:
    sys.exit("Please install tqdm: pip install tqdm")

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Batch AreTomo2 alignment tool",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "imod_dir",
        help="Input root directory, recursively searches for *.st + *.rawtlt pairs",
    )
    parser.add_argument("out_dir", help="Output root directory")
    parser.add_argument(
        "-j", "--jobs", type=int, default=2, help="Number of parallel jobs (default: 2)"
    )
    parser.add_argument(
        "-g", "--gpus", default="0,1", help="Comma-separated list of GPUs to use"
    )
    parser.add_argument(
        "--aretomo", default="AreTomo2", help="Path to AreTomo2 executable"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Maximum number of retries on failure",
    )
    parser.add_argument("--vol-z", default="0", help="-VolZ parameter (default: 0)")
    parser.add_argument(
        "--align-z", default="2000", help="-AlignZ parameter (default: 2000)"
    )
    parser.add_argument(
        "--tilt-axis",
        nargs=2,
        metavar=("AXIS", "ANGLE"),
        help="Optional -TiltAxis parameter (2 values)",
    )
    parser.add_argument(
        "--dark-tol", type=float, default=0.7, help="-DarkTol parameter (default: 0.7)"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip already aligned tilt-series (checks if MRC file exists)",
    )
    parser.add_argument(
        "--show-output",
        action="store_true",
        help="Show real-time output for the first task only",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print commands without executing them"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set the logging level",
    )

    return parser.parse_args()


def setup_environment() -> bool:
    """Attempt to set up the AreTomo environment."""
    try:
        result = subprocess.run(
            "module purge && module load AreTomo2/2 && module list",
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            text=True,
            timeout=30,
        )
        logger.info("Environment setup output:\n%s", result.stdout)
        if result.stderr:
            logger.warning("Environment setup warnings:\n%s", result.stderr)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
        logger.warning("Environment setup failed: %s", e)
        return False


def find_tilt_series(root: Path) -> List[Tuple[Path, Path]]:
    """Recursively find .st + .rawtlt file pairs."""
    pairs = []
    for st_file in root.rglob("*.st"):
        tlt_file = st_file.with_suffix(".rawtlt")
        if tlt_file.exists():
            pairs.append((st_file, tlt_file))
        else:
            logger.warning("Found %s but no matching .rawtlt file", st_file)

    if not pairs:
        logger.error("No *.st + *.rawtlt pairs found in %s", root)

    return sorted(pairs)


def build_aretomo_command(
    st: Path, tlt: Path, out_stem: Path, gpu: int, args: argparse.Namespace
) -> List[str]:
    """Build the AreTomo command line arguments."""
    cmd = [
        args.aretomo,
        "-InMrc",
        str(st),
        "-OutMrc",
        str(out_stem.with_suffix(".mrc")),
        "-AngFile",
        str(tlt),
        "-VolZ",
        str(args.vol_z),
        "-Align",
        "1",
        "-TiltCor",
        "-1",
        "-DarkTol",
        str(args.dark_tol),
        "-OutImod",
        "2",
        "-Gpu",
        str(gpu),
    ]

    if args.align_z:
        cmd.extend(["-AlignZ", str(args.align_z)])
    if args.tilt_axis:
        cmd.extend(["-TiltAxis", *args.tilt_axis])

    return cmd


def run_single_aretomo(
    st: Path,
    tlt: Path,
    out_stem: Path,
    gpu: int,
    args: argparse.Namespace,
    show_log: bool = False,
) -> Tuple[bool, str]:
    """Run AreTomo on a single tilt series."""
    log_dir = out_stem.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{st.stem}.log"
    final_mrc = out_stem.with_suffix(".mrc")

    # Skip existing if requested
    if args.skip_existing and final_mrc.exists():
        logger.info("Skipping existing output: %s", final_mrc)
        return True, str(log_file)

    cmd = build_aretomo_command(st, tlt, out_stem, gpu, args)

    # Dry run: just print the command
    if args.dry_run:
        logger.info("Would run: %s", " ".join(cmd))
        return True, "Dry run - no execution"

    # Run the command with retries
    for attempt in range(args.max_retries + 1):
        if attempt > 0:
            logger.info("Retry %d/%d for %s", attempt, args.max_retries, st.stem)
            time.sleep(5)  # Brief pause before retry

        try:
            with log_file.open("w") as log_handle:
                log_handle.write(" ".join(cmd) + "\n\n")

                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                )

                # Stream output to log and optionally to console
                for line in process.stdout:  # type: ignore
                    log_handle.write(line)
                    log_handle.flush()
                    if show_log:
                        print(line, end="")

                process.wait()

                # Check for success
                if process.returncode == 0 and final_mrc.exists():
                    logger.info("Successfully processed %s", st.stem)
                    return True, str(log_file)
                else:
                    logger.warning(
                        "Process failed for %s (return code: %d)",
                        st.stem,
                        process.returncode,
                    )

        except (OSError, subprocess.SubprocessError) as e:
            logger.error("Error running AreTomo for %s: %s", st.stem, e)

    return False, str(log_file)


def main() -> None:
    """Main function to coordinate batch processing."""
    args = parse_args()

    # Set logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # Check if AreTomo is available
    if not args.dry_run and not shutil.which(args.aretomo):
        logger.error("AreTomo2 executable not found: %s", args.aretomo)
        sys.exit(1)

    # Setup environment
    if not args.dry_run:
        logger.info("Setting up environment...")
        if not setup_environment():
            logger.warning("Environment setup may have failed, continuing anyway...")

    # Setup directories
    imod_dir = Path(args.imod_dir).resolve()
    out_dir = Path(args.out_dir).resolve()

    if not imod_dir.exists():
        logger.error("Input directory does not exist: %s", imod_dir)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)

    # Find tilt series
    logger.info("Searching for tilt series in %s", imod_dir)
    tilt_series_pairs = find_tilt_series(imod_dir)

    if not tilt_series_pairs:
        logger.error("No tilt series found. Exiting.")
        sys.exit(1)

    logger.info("Found %d tilt series to process", len(tilt_series_pairs))

    # Prepare tasks
    gpu_list = list(map(int, args.gpus.split(",")))
    tasks = []

    for i, (st_path, tlt_path) in enumerate(tilt_series_pairs):
        out_stem = out_dir / st_path.parent.relative_to(imod_dir) / st_path.stem
        gpu = gpu_list[i % len(gpu_list)]
        show_log = (
            args.show_output and i == 0
        )  # Only show output for first task if requested

        tasks.append((st_path, tlt_path, out_stem, gpu, args, show_log))

    # Process tasks
    success_list = []
    failure_list = []

    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        # Submit all tasks
        future_to_name = {
            executor.submit(run_single_aretomo, *task): task[0].stem for task in tasks
        }

        # Process results as they complete
        with tqdm(
            total=len(tasks), desc="Processing tilt series", unit="series"
        ) as pbar:
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    success, log_path = future.result()
                    if success:
                        success_list.append((name, log_path))
                    else:
                        failure_list.append((name, log_path))
                except Exception as e:
                    logger.error("Task %s failed with exception: %s", name, e)
                    failure_list.append((name, str(e)))
                finally:
                    pbar.update(1)

    # Generate summary
    logger.info(
        "Processing complete: %d success, %d failure",
        len(success_list),
        len(failure_list),
    )

    if failure_list:
        logger.warning("Failed series:")
        for name, log_info in failure_list:
            logger.warning("  %s -> %s", name, log_info)

    # Save summary to JSON
    summary: Dict[str, Any] = {
        "total": len(tasks),
        "successful": len(success_list),
        "failed": len(failure_list),
        "failed_series": [
            {"name": name, "log": log_info} for name, log_info in failure_list
        ],
        "command_args": vars(args),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "processing_time": time.process_time(),
    }

    summary_file = out_dir / "processing_summary.json"
    try:
        with summary_file.open("w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        logger.info("Summary saved to %s", summary_file)
    except IOError as e:
        logger.error("Failed to save summary: %s", e)


if __name__ == "__main__":
    main()
