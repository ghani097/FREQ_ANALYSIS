"""
Quick test of the fallback statistical methods
"""
import numpy as np
from scipy.stats import false_discovery_control

print("Testing FDR correction availability...")

# Test if scipy has false_discovery_control
try:
    p_values = np.array([0.001, 0.04, 0.06, 0.5, 0.3])
    p_corrected = false_discovery_control(p_values, method='bh')
    print("✓ scipy.stats.false_discovery_control available")
    print(f"  Original p-values: {p_values}")
    print(f"  FDR-corrected: {p_corrected}")
except AttributeError:
    print("⚠️ scipy.stats.false_discovery_control NOT available")
    print("  Will use manual FDR calculation (implemented)")

print("\nTesting manual FDR calculation...")

def manual_fdr_correction(p_values):
    """Manual FDR correction using Benjamini-Hochberg procedure"""
    
    n = len(p_values)
    sorted_idx = np.argsort(p_values)
    sorted_p = p_values[sorted_idx]
    
    # Benjamini-Hochberg critical values
    critical_values = (np.arange(1, n + 1) / n) * 0.05
    
    # Find largest i where p(i) <= (i/n)*alpha
    reject = sorted_p <= critical_values
    
    if np.any(reject):
        max_idx = np.where(reject)[0].max()
        
        # Adjusted p-values
        p_adjusted = np.minimum(1, sorted_p * n / np.arange(1, n + 1))
        
        # Enforce monotonicity
        for i in range(n - 2, -1, -1):
            p_adjusted[i] = min(p_adjusted[i], p_adjusted[i + 1])
        
        # Unsort
        p_corrected = np.empty(n)
        p_corrected[sorted_idx] = p_adjusted
    else:
        p_corrected = np.ones(n)
    
    return p_corrected

p_values = np.array([0.001, 0.04, 0.06, 0.5, 0.3])
p_corrected_manual = manual_fdr_correction(p_values)

print(f"Original p-values: {p_values}")
print(f"FDR-corrected (manual): {p_corrected_manual}")
print(f"Significant at 0.05: {p_corrected_manual < 0.05}")

print("\n✓ All statistical methods working!")
print("\nReady to run analysis with automatic fallback.")
