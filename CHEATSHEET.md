# 📝 AreTomo Batch – Quick Cheat Sheet

### 1. Install

```bash
git clone https://github.com/your-repo/aretomo-batch.git
cd aretomo-batch
pip install tqdm
```

---

### 2. Prepare data

Each tilt-series needs:

```
TS_01/TS_01.st
TS_01/TS_01.rawtlt
```

---

### 3. Run alignment

```bash
aretomo_batch.py raw_data/ aretomo_align/ \
                 -j 8 -g 0,1 \
                 --align-z 1000
```

* `-j` = concurrent jobs
* `-g` = GPU list
* `--align-z` = sample thickness (px)

Logs → `aretomo_align/logs/`
Summary → `aretomo_align/processing_summary.json`

---

### 4. Reorganise for Warp

```bash
aretomo_export_for_warp.py aretomo_align/
```

Creates Warp-ready structure:

```
aretomo_align/
├── Position_01/   # contains .mrc, .aln, logs/
├── Position_02/
└── imod/          # IMOD files preserved
```

---

✨ Done → Import directly in Warp!
