# Code Flexibility Analysis: Generic vs Hardcoded

## ✅ MOSTLY GENERIC (with some limitations)

---

## What IS Generic (Adapts Automatically):

### 1. **Group Discovery** ✅ GENERIC
```python
# Finds ANY folders in root directory
self.groups = [d.name for d in self.root_dir.iterdir() 
              if d.is_dir() and not d.name.startswith('.') 
              and d.name.lower() != 'results']
```
**Works with:**
- GroupA, GroupB ✓
- Control, Treatment ✓
- Healthy, Patient ✓
- Any folder names ✓

### 2. **Session Discovery** ✅ GENERIC
```python
# Finds ANY folders in first group
self.sessions = [d.name for d in first_group.iterdir() 
                if d.is_dir() and not d.name.startswith('.')]
```
**Works with:**
- Pre1, Post1, Pre2, Post2 ✓
- Baseline, Week1, Week2 ✓
- Any folder names ✓

### 3. **Subject Matching** ✅ GENERIC
```python
# Matches by filename - any naming scheme works
subjects1 = set(self.subjects.get(key1, []))
subjects2 = set(self.subjects.get(key2, []))
matched = sorted(list(subjects1 & subjects2))
```
**Works with:**
- SUB1Adjustment1_cleaned.set ✓
- subject_001.set ✓
- participant_ABC.set ✓
- Any .set filename ✓

---

## What Has ASSUMPTIONS (Semi-Generic):

### 1. **Pre/Post Pairing** ⚠️ REQUIRES NAMING
```python
# Searches for 'pre' and 'post' in session names (case-insensitive)
pre_sessions = sorted([s for s in sessions if 'pre' in s.lower()])
post_sessions = sorted([s for s in sessions if 'post' in s.lower()])
```

**WORKS with:**
- Pre1, Post1, Pre2, Post2 ✓
- PreTest, PostTest ✓
- pre_baseline, post_intervention ✓
- Pretreatment, Posttreatment ✓

**FAILS with:**
- Baseline, Week1 ✗ (doesn't contain "pre"/"post")
- T0, T1 ✗
- Session1, Session2 ✗

**How it pairs:**
- **Sorts alphabetically** then **zips**
- Pre1 ↔ Post1 (first pre with first post)
- Pre2 ↔ Post2 (second pre with second post)
- PreA ↔ PostA (alphabetical pairing)

### 2. **Two-Group Comparison** ⚠️ HARDCODED
```python
# ALWAYS takes first two groups
group_a, group_b = groups[0], groups[1]
```

**WORKS with:**
- 2 groups ✓ (GroupA vs GroupB)

**LIMITATIONS with:**
- 3+ groups: Only compares first two ✗
- 1 group: Fails (needs 2) ✗

**Example:**
```
If you have: Control, TreatmentA, TreatmentB
Only compares: Control vs TreatmentA
Ignores: TreatmentB
```

### 3. **File Format** ⚠️ FIXED
```python
# Only looks for .set files
set_files = list(session_path.glob('*.set'))
```

**WORKS with:**
- EEGLAB .set files ✓

**FAILS with:**
- .mat files ✗
- .edf files ✗
- Other formats ✗

---

## Summary Table

| Feature | Generic? | Notes |
|---------|----------|-------|
| Group folder names | ✅ YES | Any names work |
| Session folder names | ✅ YES | Any names work |
| Subject filenames | ✅ YES | Any .set filenames |
| Number of subjects | ✅ YES | Works with any n ≥ 2 |
| Pre/Post identification | ⚠️ PARTIAL | Must contain "pre"/"post" |
| Session pairing | ⚠️ PARTIAL | Alphabetical zip |
| Number of groups | ❌ NO | Fixed to 2 groups |
| File format | ❌ NO | Only .set files |
| Frequency bands | ✅ YES | Configurable in config |

---

## Examples of What Works:

### ✅ Example 1: Your Current Setup
```
LIFE_Data_UPD/
  ├── GroupA/
  │   ├── Pre1/
  │   ├── Post1/
  │   ├── Pre2/
  │   └── Post2/
  └── GroupB/
      ├── Pre1/
      ├── Post1/
      ├── Pre2/
      └── Post2/
```
**Result:** Compares GroupA vs GroupB for Post1-Pre1 and Post2-Pre2 ✓

### ✅ Example 2: Different Names
```
MyData/
  ├── Control/
  │   ├── pretest/
  │   └── posttest/
  └── Treatment/
      ├── pretest/
      └── posttest/
```
**Result:** Compares Control vs Treatment for posttest-pretest ✓

### ✅ Example 3: Multiple Time Points
```
Study/
  ├── Healthy/
  │   ├── Pre_Baseline/
  │   ├── Post_Week1/
  │   ├── Pre_Month2/
  │   └── Post_Month3/
  └── Patient/
      ├── Pre_Baseline/
      ├── Post_Week1/
      ├── Pre_Month2/
      └── Post_Month3/
```
**Result:** 
- Compares Post_Month3 vs Pre_Month2 (last pair)
- Compares Post_Week1 vs Pre_Baseline (first pair)
- (Alphabetically sorted and zipped) ✓

---

## Examples of What DOESN'T Work:

### ❌ Example 1: Three Groups
```
Data/
  ├── Control/
  ├── LowDose/
  └── HighDose/
```
**Problem:** Only compares Control vs LowDose, ignores HighDose

### ❌ Example 2: No Pre/Post Keywords
```
Data/
  ├── GroupA/
  │   ├── Baseline/
  │   └── Week4/
  └── GroupB/
      ├── Baseline/
      └── Week4/
```
**Problem:** Can't identify which is "pre" and which is "post"

### ❌ Example 3: Single Group
```
Data/
  └── AllSubjects/
      ├── Pre/
      └── Post/
```
**Problem:** Needs 2 groups to compare

---

## How to Make it Work for Different Structures:

### Option 1: **Use Pre/Post Keywords** (Easiest)
Name your sessions with "pre" or "post" somewhere:
- `Session1_Pre` and `Session2_Post` ✓
- `T0_pretreatment` and `T1_posttreatment` ✓

### Option 2: **Modify the Code** (For Non-Pre/Post Designs)
Change lines 44-45 in `py_analyzer.py`:
```python
# Instead of:
pre_sessions = sorted([s for s in sessions if 'pre' in s.lower()])
post_sessions = sorted([s for s in sessions if 'post' in s.lower()])

# Use:
pre_sessions = sorted([s for s in sessions if 'baseline' in s.lower()])
post_sessions = sorted([s for s in sessions if 'week' in s.lower()])
```

### Option 3: **Add GUI Session Selector** (Future Enhancement)
Could add dropdowns to manually select which sessions to compare instead of automatic Pre/Post detection.

---

## Recommendation:

**Your current code IS generic enough for most standard EEG studies with:**
- 2 groups
- Pre/Post design
- Multiple time points
- Any group/subject naming

**But needs modification for:**
- 3+ group comparisons
- Non-pre/post designs
- Different file formats

**For your LIFE_Data_UPD structure:** Works perfectly as-is! ✓
