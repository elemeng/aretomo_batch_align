# 🎯 AreTomo Batch Processing Pipeline

A **lightweight**, **high-throughput** toolchain for automated tilt-series alignment.

---

### **Why do you need this?**

To reconstruct tomograms in **Warp**, tilt-series (TS) must first be **aligned**.

One of the most powerful tools for this is **AreTomo2**. But running it manually usually means:

1. Opening each TS folder
2. Running AreTomo2
3. Waiting for it to finish
4. Moving to the next folder … and repeating *dozens of times*

This wrapper eliminates the tedium by turning alignment into a **single command pipeline**:

1. ⚡ **Align** all cryo tilt-series in parallel with **AreTomo2** (using any number of GPUs/CPUs).
2. 📂 **Re-package** results into a Warp-ready folder structure instantly recognised for tomogram reconstruction.

✨ No manual edits. No endless copy–paste.
Just **two commands**, and you’re ready for Warp’s 3-D CTF estimation, subtomogram averaging, or tomogram reconstruction.

---

## 🚀 What the pipeline does

| Step | Script                       | Input               | Output                                | Purpose                                          |
| ---- | ---------------------------- | ------------------- | ------------------------------------- | ------------------------------------------------ |
| 1    | `aretomo_batch.py`           | `*.st` + `*.rawtlt` | `aretomo_align/` + logs + JSON report | Run AreTomo2 across GPUs/CPUs                    |
| 2    | `aretomo_export_for_warp.py` | `aretomo_align/`    | clean, Warp-ready tree                | Delete temps, rename IMOD files, organise neatly |

**Example resulting structure:**

```
aretomo_align/
├── Position_01/
│   ├── Position_01.mrc     # aligned tilt-series
│   ├── Position_01.aln     # AreTomo2 alignment
│   └── logs/               # console log for this series
├── Position_02/
│   └── …
└── imod/                   # all IMOD files preserved
    ├── Position_01/
    │   ├── Position_01.tlt
    │   ├── Position_01.xf
    │   └── …
    └── Position_02/
```

Warp’s *Import Tomograms* dialog will recognise each `Position_XX` folder instantly.

---

## ⚡ Installation

```bash
git clone https://github.com/your-repo/aretomo-batch.git
cd aretomo-batch

# (optional) add to PATH
ln -s "$PWD"/aretomo_batch.py ~/bin/
ln -s "$PWD"/aretomo_export_for_warp.py ~/bin/
chmod +x ~/bin/*.py
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Then start aligning your TS! 🚀

**Requirements:**

* Python ≥ 3.7
* [`tqdm`](https://pypi.org/project/tqdm/) → progress bars

Install with:

```bash
pip install tqdm
```

> **Note:** AreTomo2 itself is **not bundled**. Use the binary provided by your facility or your own installation.

---

## 🏁 Quick start

### 1. Prepare your data

Each tilt-series (`xxx.st`) must have a matching angle file (`xxx.rawtlt`) in the same folder:

```
imod/
├── TS_01/
│   ├── TS_01.st
│   ├── TS_01.rawtlt
├── TS_02/
│   └── …
```

### 2. Run alignment (2-GPU example)

```bash
aretomo_batch.py raw_data/ aretomo_align/ \
                 -j 8 -g 0,1 \
                 --align-z 800 \
                 --tilt-axis 0.0 1
```

**Flag explanation:**

| Flag                | Meaning                              |
| ------------------- | ------------------------------------ |
| `-j 8`              | run 8 tilt-series concurrently       |
| `-g 0,1`            | distribute work across GPU 0 and 1   |
| `--align-z 800`     | alignment volume thickness in pixels |
| `--tilt-axis 0.0 1` | (optional) fixed tilt axis           |

While running you’ll see:

```
Aligning:  43%|████▎     | 22/51  [12:03<15:41,  3.1 s/series]
```

* Logs for each series → `aretomo_align/logs/`
* Run summary → `aretomo_align/processing_summary.json`

### 3. Re-organise for Warp

```bash
aretomo_export_for_warp.py aretomo_align/
```

This will:

* 🗑️ delete bulky `*_st.mrc` files
* ✍️ rename IMOD files (`_st.tlt` → `.tlt`, etc.)
* 📂 move `.aln`, `.mrc`, and `logs/` into per-series folders
* 📝 generate `cleanup_summary.json`

✅ Import `aretomo_align/` directly in Warp.

---

## 🔧 Command-line reference

### `aretomo_batch.py`

```
usage: aretomo_batch.py [options] imod_dir out_dir
```

* **Positional arguments:**

  * `imod_dir` → root folder with `*.st` + `*.rawtlt` (recursively searched)
  * `out_dir` → destination for results

* **Key options:**

  * `-j, --jobs` → number of concurrent series (default: 2)
  * `-g, --gpus` → GPU list, e.g. `0,1,2` (default: "0,1")
  * `--aretomo` → path to AreTomo2 binary (default: `AreTomo2`)
  * `--skip-existing` → skip already aligned series
  * `--show-output` → stream live log of the first job
  * `--dry-run` → print commands without running
  * plus advanced params (`--align-z`, `--vol-z`, `--tilt-axis`, etc.)

### `aretomo_export_for_warp.py`

```
usage: aretomo_export_for_warp.py root
```

* `root` = the `aretomo_align/` output folder

---

## ❓ FAQ

**Q1:** How do I point to my own AreTomo2 binary?
👉 If `AreTomo2` is in your `$PATH`:

```bash
aretomo_batch.py --aretomo AreTomo2 …
```

👉 Otherwise, use the absolute path:

```bash
aretomo_batch.py --aretomo /path/to/AreTomo2 …
```

**Q2:** Can I run this on SLURM?
👉 Yes – either use a job array (1 series per task) or let the script handle GPUs via `-j` and `-g`.

**Q3:** Can I resume an interrupted run?
👉 Yes – run again with `--skip-existing` to skip finished series.

**Q4:** Where do I find logs?
👉 Each series has its own `logs/` folder.

**Q5:** What about IMOD files?
👉 They’re preserved in `aretomo_align/imod/`. Only temporary files (`*_st.mrc`) are deleted.

---

## 📊 Example benchmark

* Dataset: 52 tilt-series, 4k × 6k × 41 views, 1.7 Å/px
* Hardware: 2 × RTX-4090, 32 CPU threads
* Command: `aretomo_batch.py … -j 8 -g 0,1 --align-z 2000`
* Runtime: **\~50 min** (≈ 1 min per series)
* GPU utilisation: \~95 % steady

---

## 📚 Citation & License

If this pipeline helps your research, please cite:

> **AreTomo: An integrated software package for automated marker-free, motion-corrected cryo-electron tomographic alignment and reconstruction**
> *Journal of Structural Biology: X, Vol 6, 2022*

Released under the **MIT License** – free to use, modify, and share. No warranty.

---

## 🐞 Feedback

* 💬 Report issues on [GitHub](https://github.com/your-repo/aretomo-batch)

---

✨ **Happy aligning, happy tomograms!**


