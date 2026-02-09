# CRITICAL BUG: Identical Plots for Post1-Pre1 and Post2-Pre2

## SYMPTOM
Running EEG analysis produces **EXACTLY IDENTICAL** plots for:
- Post1_vs_Pre1 comparison
- Post2_vs_Pre2 comparison

Even when changing parameters (epoch length, p-value threshold), the plots remain identical. This suggests data is NOT being loaded correctly despite different labels.

---

## CURRENT CONTEXT

### Project Structure
```
E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\python_implementation\

Main files:
- py_gui_main.py        # PyQt6 GUI + AnalysisWorker thread
- py_analyzer.py        # Core analysis (loads data, runs stats)
- py_visualizer.py      # Creates matplotlib figures
- py_data_loader.py     # Discovers files and loads .set files
- py_config.py          # Constants and parameters

Data folder:
LIFE_Data_UPD/
├── GroupA/
│   ├── Pre1/
│   │   ├── SUB1Adjustment1_cleaned.set
│   │   ├── SUB2Adjustment1_cleaned.set
│   │   └── ... (n=6-7 subjects)
│   ├── Post1/
│   │   └── [matching subjects]
│   ├── Pre2/
│   │   ├── SUB1Adjustment2_cleaned.set  # ← Note: Adjustment2
│   │   └── [matching subjects]
│   └── Post2/
│       └── [matching subjects]
└── GroupB/
    └── [same structure, n=2 subjects]
```

### What Was Recently Changed
We modified the code to support **multiple Pre/Post session pairs**:

**py_analyzer.py** (lines 31-106):
```python
def run_analysis(self, config):
    # Detect all Pre/Post session pairs
    pre_sessions = [s for s in sessions if 'pre' in s.lower()]
    post_sessions = [s for s in sessions if 'post' in s.lower()]
    
    # Sort and zip them
    pre_sessions.sort()
    post_sessions.sort()
    session_pairs = list(zip(pre_sessions, post_sessions))
    
    # Process each pair
    all_results = {}
    for pre_sess, post_sess in session_pairs:
        comparison_name = f"{post_sess}_vs_{pre_sess}"
        # Load data and analyze
        results = self._analyze_single_comparison(...)
        all_results[comparison_name] = results
    
    return all_results
```

**py_gui_main.py** (lines 35-96):
The AnalysisWorker detects multi-comparison results and visualizes each separately.

### Previous Testing
1. ✅ Created `test_post1_vs_post2.py` - confirmed Post1 and Post2 **DATA FILES** are different (MD5 hashes differ)
2. ✅ Added comparison_name to plot titles and filenames
3. ✅ Verified labels show correctly (Post1_vs_Pre1, Post2_vs_Pre2)

**BUT**: Despite different labels, the actual plot data appears IDENTICAL.

---

## SUSPECTED ROOT CAUSES

### Theory 1: Data Loading Issue
**Hypothesis**: Code labels comparisons correctly but loads the SAME data twice.

**Check**:
- Does `_analyze_single_comparison()` actually receive different `pre_sess`/`post_sess` each iteration?
- Are `matched_subjects` different for each session pair?
- Is `py_data_loader.load_power_data()` called with correct session paths?

### Theory 2: Variable Reuse/Caching
**Hypothesis**: Data arrays are being reused by reference instead of copied.

**Check**:
- Are numpy arrays being shallow-copied somewhere?
- Is there a cache mechanism we're not clearing between comparisons?
- Are `data_a` and `data_b` in analyzer reused across loop iterations?

### Theory 3: Session Pairing Logic Broken
**Hypothesis**: Both comparisons are actually using Pre1/Post1 data despite labels.

**Check**:
- Print actual session folder names being used in each iteration
- Verify `pre_sessions.sort()` and `post_sessions.sort()` produce expected order
- Check if file discovery is actually finding Pre2/Post2 folders

### Theory 4: Worker Thread Issue
**Hypothesis**: GUI worker thread is not calling analyzer correctly for multi-comparisons.

**Check**:
- Does `run_analysis()` return the correct nested structure?
- Is the worker loop actually iterating with different data per comparison?

---

## INVESTIGATION PLAN

### Step 1: Add Diagnostic Logging
Modify `py_analyzer.py` to print:
```python
def run_analysis(self, config):
    print(f"\n=== ANALYZER: Found {len(session_pairs)} session pairs ===")
    for i, (pre_sess, post_sess) in enumerate(session_pairs):
        print(f"\nPair {i+1}: {pre_sess} vs {post_sess}")
        
        # Inside _analyze_single_comparison:
        print(f"  Pre path: {pre_path}")
        print(f"  Post path: {post_path}")
        print(f"  Matched subjects: {matched_subjects}")
        print(f"  Data shape Group A: {data_a.shape}")
        print(f"  Data shape Group B: {data_b.shape}")
        print(f"  First 3 values Group A Pre: {data_a[0, :3, 0]}")
        print(f"  First 3 values Group A Post: {data_a[0, :3, 1]}")
```

### Step 2: Create Verification Test
```python
# test_identical_plots_debug.py
import sys
import numpy as np
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from py_analyzer import EEGFrequencyAnalyzer

config = {
    'data_dir': r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\LIFE_Data_UPD',
    'output_dir': 'DEBUG_OUTPUT',
    'frequency_range': [8, 13],
    'band_name': 'Alpha',
    'stat_method': 'independent_ttest',
    'skip_fdr': True,
    'process_all_sessions': True,
    'alpha': 0.05
}

analyzer = EEGFrequencyAnalyzer()
results = analyzer.run_analysis(config)

print("\n=== RESULTS STRUCTURE ===")
for comp_name, comp_results in results.items():
    print(f"\nComparison: {comp_name}")
    for band_name, band_data in comp_results.items():
        t_vals = band_data['t_values']
        print(f"  {band_name}: t-values shape={t_vals.shape}")
        print(f"    Min/Max t-values: {t_vals.min():.4f} / {t_vals.max():.4f}")
        print(f"    Mean t-value: {t_vals.mean():.4f}")
        print(f"    Significant channels: {np.sum(band_data['mask'])}")

# Check if t-values are identical
comp_names = list(results.keys())
if len(comp_names) >= 2:
    band = 'Alpha'
    t1 = results[comp_names[0]][band]['t_values']
    t2 = results[comp_names[1]][band]['t_values']
    
    print(f"\n=== COMPARING {comp_names[0]} vs {comp_names[1]} ===")
    print(f"Are t-values identical? {np.allclose(t1, t2)}")
    print(f"Max absolute difference: {np.abs(t1 - t2).max()}")
```

### Step 3: Check Data Loader
```python
# test_data_loader_sessions.py
from py_data_loader import EEGDataLoader

loader = EEGDataLoader(r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\LIFE_Data_UPD')
structure = loader.scan_directory()

print("=== DISCOVERED STRUCTURE ===")
for group, sessions in structure.items():
    print(f"\n{group}:")
    for session, subjects in sessions.items():
        print(f"  {session}: {subjects}")

# Test loading from different sessions
group = list(structure.keys())[0]
sessions = list(structure[group].keys())

print(f"\n=== TESTING DATA LOADING ===")
for session in sessions[:2]:  # Test first 2 sessions
    subjects = structure[group][session]
    if subjects:
        subject = subjects[0]
        data = loader.load_power_data(group, session, subject, freq_range=[8, 13])
        print(f"{session}/{subject}: shape={data.shape}, mean={data.mean():.6e}")
```

### Step 4: Examine Actual Code Flow
Look at these specific areas:

1. **py_analyzer.py line 31-106**: Session pairing loop
   - Verify loop actually iterates multiple times
   - Verify different paths used each iteration

2. **py_analyzer.py line 110-250**: `_analyze_single_comparison()`
   - Check if this creates fresh data structures
   - Verify no global variables being reused

3. **py_data_loader.py**: `load_power_data()`
   - Check for any caching mechanism
   - Verify it uses session parameter correctly

4. **py_gui_main.py line 35-96**: Worker thread
   - Verify it iterates through all comparisons
   - Check if visualizer gets fresh data each time

---

## EXPECTED OUTCOMES

### If Code is Correct:
- Diagnostic logs show different session paths
- t-values differ between comparisons
- `np.allclose(t1, t2)` returns False
- Mean t-values are substantially different

### If Bug Exists:
- Session paths might be identical despite different labels
- t-values are identical (or nearly so)
- Data shapes might be identical
- Matched subjects might be identical

---

## FILES TO EXAMINE FIRST

Priority order:
1. **py_analyzer.py** lines 31-106 (session pairing)
2. **py_analyzer.py** lines 110-250 (_analyze_single_comparison)
3. **py_data_loader.py** lines 68-77 (get_matched_subjects)
4. **py_data_loader.py** lines 79-140 (load_power_data)
5. **py_gui_main.py** lines 35-96 (worker thread visualization loop)

---

## ADDITIONAL INFORMATION

### Environment
- Windows system
- Python with MNE-Python, PyQt6, numpy, scipy
- Working directory: `E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\python_implementation`

### Recent Work History
- Initially only analyzed Pre1/Post1 (worked correctly)
- Modified to support multiple Pre/Post pairs
- Confirmed file names differ (Adjustment1 vs Adjustment2)
- Confirmed file contents differ (MD5 hashes)
- But resulting plots are IDENTICAL

### What User Has Tried
- Changed epoch length parameter → plots still identical
- Changed p-value threshold → plots still identical
- Checked file hashes → files ARE different
- Checked plot labels → labels are correct

This strongly suggests a **data loading or variable reuse bug**, not a data problem.

---

## DELIVERABLE REQUESTED

1. **Root cause identification**: Why are plots identical?
2. **Fix**: Modify code to load correct data for each comparison
3. **Verification**: Test showing plots are now different
4. **Summary**: Brief explanation of what was wrong

Please investigate systematically with diagnostic prints/tests before making changes.
