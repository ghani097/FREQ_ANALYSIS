"""
Diagnostic: Lenient cluster-based permutation + raw p-value dump
Supports any data directory with (Group A / Group B) x (sessions).

Lenient settings:
  - cluster_alpha = 0.10  (more channels eligible to form clusters)
  - tail = 0              (two-tailed)
  - n_permutations = 5000 (stable estimate)
  - Spatial adjacency via MNE standard_1020 montage (RECOMMENDED)
    -- set ADJACENCY_METHOD = 'none' to reproduce the old inflated-null behaviour

Also prints raw uncorrected channel t-test p-values so you can see
what range they actually fall in.
"""

import sys
import os
import warnings
import numpy as np
from pathlib import Path
from scipy import stats
from scipy.stats import ttest_ind
from mne.stats import permutation_cluster_test
from mne.time_frequency import psd_array_welch
import mne

# ── project root on path ────────────────────────────────────────────────────
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from py_data_loader import EEGDataLoader
from py_config import FREQUENCY_BANDS

# ── settings ─────────────────────────────────────────────────────────────────
DATA_DIR         = Path(r"E:/GIT_HUB_MAIN/FREQ_ANALYSIS/DATA_PAK_KIDS")
GROUPS           = ["Group A", "Group B"]
BASELINE_SESSION = "pre"
POST_SESSIONS    = ["post6W", "post12W", "post16W"]   # all comparisons to run

FREQ_RANGE       = (1, 45)
EPOCH_LEN        = 2.0       # seconds (for Welch window)
CLUSTER_ALPHA    = 0.10      # LENIENT: threshold for cluster formation
N_PERMS          = 5000      # many permutations for stable p-values
TAIL             = 0         # two-tailed
MIN_COMMON       = 3         # minimum common channels to proceed
MAX_EXCL_FRAC    = 0.25      # max fraction of subjects to exclude for channel alignment
ADJACENCY_METHOD = 'mne'     # 'mne' | 'data' | 'none'


# ── helpers ──────────────────────────────────────────────────────────────────

def load_psd(filepath: Path, freq_range, epoch_len):
    loader = EEGDataLoader(str(DATA_DIR))
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        raw = loader.load_set_file(filepath, resample_rate=None, ignore_epochs=True)

    sfreq = raw.info["sfreq"]
    n_fft = min(int(epoch_len * sfreq), raw.get_data().shape[-1])

    data = raw.get_data()  # (n_ch, n_times)
    psds, freqs = psd_array_welch(
        data,
        sfreq=sfreq,
        fmin=freq_range[0],
        fmax=freq_range[1],
        n_fft=n_fft,
        n_overlap=n_fft // 2,
        verbose=False,
    )
    return {
        "psds": psds,
        "freqs": freqs,
        "ch_names": [c.upper().strip() for c in raw.ch_names],
        "info": raw.info,
        "subject": filepath.stem,
    }


def band_power(psd_dict, band_range, channels):
    ch = psd_dict["ch_names"]
    freqs = psd_dict["freqs"]
    mask = (freqs >= band_range[0]) & (freqs <= band_range[1])
    idx = [ch.index(c) for c in channels if c in ch]
    return np.mean(psd_dict["psds"][idx][:, mask], axis=1)  # (n_ch,)


def common_channels(psd_lists):
    """Intersection of channel names across all PSD dicts."""
    sets = [set(p["ch_names"]) for p in psd_lists]
    return sorted(set.intersection(*sets))


def adjacency_from_3d(info, dist_threshold=0.05):
    """Build adjacency from 3D electrode positions (avoids 2D-projection failures).

    dist_threshold: metres — 0.05 m (5 cm) gives ~4-6 nearest neighbours
    for a standard 64-channel 10-10 layout.
    """
    from scipy.sparse import csr_matrix
    from scipy.spatial.distance import cdist

    pos = np.array([ch['loc'][:3] for ch in info['chs']])
    valid = np.any(pos != 0, axis=1)
    if not np.any(valid):
        return None
    dists = cdist(pos, pos)
    adj = (dists < dist_threshold) & (dists > 0)
    return csr_matrix(adj.astype(np.float64))


def get_adjacency(info, method='mne'):
    """Build spatial adjacency matrix.  method: 'mne' | 'data' | 'none'"""
    if method == 'none':
        return None
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore')
        if method == 'data':
            try:
                adj = adjacency_from_3d(info)
                if adj is not None:
                    return adj
            except Exception as e:
                print(f"  Data adjacency failed ({e}), falling back to MNE montage")
        # MNE standard_1020 — set montage then build from 3D positions
        try:
            info_copy = info.copy()
            montage = mne.channels.make_standard_montage('standard_1020')
            info_copy.set_montage(montage, on_missing='ignore', verbose=False)
            adj = adjacency_from_3d(info_copy)
            if adj is not None:
                return adj
        except Exception as e:
            print(f"  MNE adjacency failed ({e}), no spatial constraint used")
        return None


def sep(title=""):
    w = 72
    if title:
        pad = max(0, w - len(title) - 4)
        print(f"\n{'='*2} {title} {'='*(pad)}")
    else:
        print("=" * w)


# ── channel alignment helpers ─────────────────────────────────────────────────

def align_channels(psd_list, min_common=MIN_COMMON, max_excl_frac=MAX_EXCL_FRAC):
    """Find common channels across all PSDs, progressively excluding worst subjects.

    Returns (common_ch, ref_info, excluded_ids) or (None, None, set) on failure.
    """
    from collections import defaultdict

    subj_ch_sets = defaultdict(list)
    info_candidates = []

    for p in psd_list:
        subj_ch_sets[p["subject"]].append(set(p["ch_names"]))
        info_candidates.append((p["info"], set(p["ch_names"])))

    # Per-subject common channels (intersection of their own sessions)
    subj_common = {sid: set.intersection(*sets) for sid, sets in subj_ch_sets.items()}

    all_sets = list(subj_common.values())
    common = sorted(set.intersection(*all_sets))
    excluded = set()

    if len(common) < min_common:
        worst = sorted(subj_common.items(), key=lambda x: len(x[1]))
        max_excl = max(1, int(len(subj_common) * max_excl_frac))

        for sid, _ in worst:
            if len(common) >= min_common or len(excluded) >= max_excl:
                break
            remaining = {k: v for k, v in subj_common.items()
                         if k not in excluded and k != sid}
            if not remaining:
                break
            new_common = sorted(set.intersection(*remaining.values()))
            if len(new_common) > len(common):
                common = new_common
                excluded.add(sid)
                print(f"    Excluding {sid} -> {len(common)} common channels")

    if len(common) < min_common:
        return None, None, excluded

    total_unique = sorted(set.union(*subj_common.values()))

    # Pick the best reference Info (maximises channel coverage)
    ch_freq = {}
    for ch_set in subj_common.values():
        for ch in ch_set:
            ch_freq[ch] = ch_freq.get(ch, 0) + 1

    total_unique_set = set(total_unique)

    def ref_score(candidate):
        info, ch_set = candidate
        overlap = ch_set & total_unique_set
        rarity = sum(1.0 / ch_freq.get(ch, 1) for ch in overlap)
        return (len(overlap), rarity, len(ch_set))

    ref_info_raw = max(info_candidates, key=ref_score)[0]
    ref_ch = list(ref_info_raw.ch_names)
    common_in_ref = [ch for ch in common if ch in ref_ch]

    if len(common_in_ref) < min_common:
        return None, None, excluded

    pick_idx = [ref_ch.index(ch) for ch in common_in_ref]
    ref_info = mne.pick_info(ref_info_raw.copy(), pick_idx)

    return common_in_ref, ref_info, excluded


def compute_diffs(pre_psds, post_psds, band_range, common_ch):
    """Post-Pre band power differences for matched subjects. Returns (n_subj, n_ch)."""
    out = []
    for pre_p, post_p in zip(pre_psds, post_psds):
        pre_ch = pre_p["ch_names"]
        post_ch = post_p["ch_names"]
        freq_mask = (pre_p["freqs"] >= band_range[0]) & (pre_p["freqs"] <= band_range[1])
        pre_idx  = [pre_ch.index(c)  for c in common_ch if c in pre_ch]
        post_idx = [post_ch.index(c) for c in common_ch if c in post_ch]
        if len(pre_idx) != len(common_ch) or len(post_idx) != len(common_ch):
            continue  # subject missing some channels — skip
        bp_pre  = np.mean(pre_p["psds"][pre_idx][:, freq_mask],  axis=1)
        bp_post = np.mean(post_p["psds"][post_idx][:, freq_mask], axis=1)
        out.append(bp_post - bp_pre)
    return np.array(out) if out else None


def run_band(diff_a, diff_b, common_ch, adjacency):
    """Run raw t-tests + cluster permutation for one band. Returns summary dict."""
    n_a, n_b = len(diff_a), len(diff_b)
    n_ch = diff_a.shape[1]

    # Raw t-tests
    t_vals = np.zeros(n_ch)
    p_raw  = np.zeros(n_ch)
    for c in range(n_ch):
        t_vals[c], p_raw[c] = ttest_ind(diff_a[:, c], diff_b[:, c])

    print(f"  Group A: n={n_a}  Group B: n={n_b}  Channels: {n_ch}")
    print(f"\n  Raw uncorrected t-test p-values (per channel):")
    print(f"  {'Channel':<12}  {'t':>8}  {'p_raw':>10}")
    print(f"  {'-'*36}")
    for c, ch in enumerate(common_ch):
        star = " *" if p_raw[c] < 0.05 else "  "
        print(f"  {ch:<12}  {t_vals[c]:>8.3f}  {p_raw[c]:>10.4f}{star}")

    print(f"\n  p_raw: min={p_raw.min():.4f}  median={np.median(p_raw):.4f}  max={p_raw.max():.4f}")
    print(f"  Channels p<.05: {np.sum(p_raw<0.05)}/{n_ch}   "
          f"p<.10: {np.sum(p_raw<0.10)}/{n_ch}   p<.20: {np.sum(p_raw<0.20)}/{n_ch}")

    # Cluster permutation
    df = n_a + n_b - 2
    threshold = stats.t.ppf(1 - CLUSTER_ALPHA, df)
    print(f"\n  Cluster threshold (t, alpha={CLUSTER_ALPHA}, df={df}): {threshold:.3f}")

    best_p = 1.0
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore")
            t_obs, clusters, cluster_pv, H0 = permutation_cluster_test(
                [diff_a, diff_b],
                n_permutations=N_PERMS,
                threshold=threshold,
                tail=TAIL,
                adjacency=adjacency,
                n_jobs=-1,
                verbose=False,
            )

        print(f"\n  Cluster permutation ({len(clusters)} cluster(s)):")
        if len(clusters) == 0:
            print(f"    No clusters — max |t|={np.max(np.abs(t_obs)):.3f} < threshold={threshold:.3f}")
        else:
            print(f"  {'#':>4}  {'Size':>5}  {'p_cluster':>10}  Channels")
            print(f"  {'-'*70}")
            for i, (cl, pv) in enumerate(zip(clusters, cluster_pv)):
                chs_idx = cl[0] if isinstance(cl, tuple) else np.where(cl)[0]
                chs_names = [common_ch[j] for j in chs_idx]
                sig = " ***" if pv<0.001 else (" **" if pv<0.01 else (" *" if pv<0.05 else (" ~" if pv<0.10 else "")))
                print(f"  {i+1:>4}  {len(chs_idx):>5}  {pv:>10.4f}{sig}  {', '.join(chs_names)}")
            best_p = min(cluster_pv)
            print(f"\n  Best cluster p = {best_p:.4f}")

        if len(H0) > 0:
            print(f"\n  H0: 5th={np.percentile(H0,5):.2f}  50th={np.percentile(H0,50):.2f}  "
                  f"95th={np.percentile(H0,95):.2f}  obs_max={np.max(np.abs(t_obs)):.2f}")

    except Exception as e:
        print(f"  Cluster test FAILED: {e}")

    return {"min_p_raw": p_raw.min(), "n_sig_05": int(np.sum(p_raw<0.05)), "best_cluster_p": best_p}


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    sep("Loading data")

    all_sessions = [BASELINE_SESSION] + POST_SESSIONS
    all_psds = {g: {s: {} for s in all_sessions} for g in GROUPS}

    for g in GROUPS:
        for s in all_sessions:
            session_dir = DATA_DIR / g / s
            if not session_dir.exists():
                print(f"  WARN: {g}/{s} does not exist")
                continue
            files = sorted(session_dir.glob("*.set"))
            print(f"  {g}/{s}: {len(files)} subjects")
            for f in files:
                try:
                    p = load_psd(f, FREQ_RANGE, EPOCH_LEN)
                    all_psds[g][s][p["subject"]] = p
                except Exception as e:
                    print(f"    WARN {f.name}: {e}")

    sep("Analysis settings")
    print(f"  cluster_alpha   : {CLUSTER_ALPHA}")
    print(f"  n_permutations  : {N_PERMS}")
    print(f"  tail            : {TAIL}  (0=two-tailed)")
    print(f"  adjacency_method: {ADJACENCY_METHOD}")
    print(f"  Comparisons     : {[f'{p} vs {BASELINE_SESSION}' for p in POST_SESSIONS]}")

    all_summary = []  # collect across comparisons

    # ── Loop over each post session ───────────────────────────────────────────
    for post_sess in POST_SESSIONS:
        comparison = f"{post_sess} vs {BASELINE_SESSION}"
        sep(f"COMPARISON: {comparison}")

        # Match subjects (must appear in BOTH pre and post for BOTH groups)
        matched = {}
        for g in GROUPS:
            pre_dict  = all_psds[g].get(BASELINE_SESSION, {})
            post_dict = all_psds[g].get(post_sess, {})
            ids = sorted(set(pre_dict) & set(post_dict))
            matched[g] = {
                "pre":  [pre_dict[i]  for i in ids],
                "post": [post_dict[i] for i in ids],
                "ids": ids
            }
            print(f"  {g}: {len(ids)} matched subjects  "
                  f"({', '.join(ids)})")

        # Align channels with progressive exclusion
        all_flat = [p for g in GROUPS for role in ("pre", "post")
                    for p in matched[g][role]]

        print(f"\n  Channel alignment...")
        common_ch, common_info, excluded = align_channels(all_flat)

        if common_ch is None:
            print(f"  SKIP: fewer than {MIN_COMMON} common channels")
            continue

        print(f"  Common channels ({len(common_ch)}): {', '.join(common_ch)}")
        if excluded:
            # Remove excluded subjects
            for g in GROUPS:
                matched[g]["pre"]  = [p for p in matched[g]["pre"]
                                      if p["subject"] not in excluded]
                matched[g]["post"] = [p for p in matched[g]["post"]
                                      if p["subject"] not in excluded]

        # Build adjacency for this channel set
        print(f"\n  Building adjacency (method={ADJACENCY_METHOD})...")
        adjacency = get_adjacency(common_info, method=ADJACENCY_METHOD)
        if adjacency is not None:
            nc = np.array(adjacency.sum(axis=1)).ravel()
            print(f"  Adjacency: {adjacency.shape}, {adjacency.nnz} entries  "
                  f"(neighbours: min={nc.min():.0f} mean={nc.mean():.1f} max={nc.max():.0f})")
        else:
            print(f"  Adjacency: None")

        # ── Per-band analysis ────────────────────────────────────────────────
        comp_summary = []

        for band_name, band_range in FREQUENCY_BANDS.items():
            sep(f"{comparison} | {band_name}  ({band_range[0]}-{band_range[1]} Hz)")

            diff_a = compute_diffs(matched["Group A"]["pre"], matched["Group A"]["post"],
                                   band_range, common_ch)
            diff_b = compute_diffs(matched["Group B"]["pre"], matched["Group B"]["post"],
                                   band_range, common_ch)

            if diff_a is None or diff_b is None or len(diff_a) < 2 or len(diff_b) < 2:
                print(f"  SKIP: not enough data")
                continue

            res = run_band(diff_a, diff_b, common_ch, adjacency)
            res["comparison"] = comparison
            res["band"] = band_name
            comp_summary.append(res)
            all_summary.append(res)

        # Per-comparison mini-summary
        if comp_summary:
            print(f"\n  --- {comparison} summary ---")
            print(f"  {'Band':<10}  {'min_p_raw':>10}  {'n_p<.05':>8}  {'best_cluster_p':>15}")
            print(f"  {'-'*50}")
            for r in comp_summary:
                print(f"  {r['band']:<10}  {r['min_p_raw']:>10.4f}  "
                      f"{r['n_sig_05']:>8}  {r['best_cluster_p']:>15.4f}")

    # ── Grand summary ─────────────────────────────────────────────────────────
    sep("GRAND SUMMARY")
    print(f"  {'Comparison':<22}  {'Band':<8}  {'min_p_raw':>10}  {'n_p<.05':>8}  {'cluster_p':>10}")
    print(f"  {'-'*66}")
    for r in all_summary:
        sig = " *" if r["best_cluster_p"] < 0.05 else (" ~" if r["best_cluster_p"] < 0.10 else "  ")
        print(f"  {r['comparison']:<22}  {r['band']:<8}  {r['min_p_raw']:>10.4f}  "
              f"{r['n_sig_05']:>8}  {r['best_cluster_p']:>10.4f}{sig}")
    sep()
    print("\nDone.")


if __name__ == "__main__":
    main()
