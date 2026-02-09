"""
Diagnostic script to check actual data values
"""

import numpy as np
from pathlib import Path
from py_data_loader import EEGDataLoader

def check_data_values():
    """Check if data is being loaded correctly"""
    
    root_dir = Path(r'E:\GIT_HUB_MAIN\EEG-FREQ-Based_Analysis\eeg_ft_stats\FreqAnalysis_UG\LIFE_Data_UPD')
    loader = EEGDataLoader(root_dir)
    
    print("="*80)
    print("DATA VALUE DIAGNOSTIC")
    print("="*80)
    
    # Load one subject from each group
    groups = ['GroupA', 'GroupB']
    sessions = ['Pre1', 'Post1']
    
    for group in groups:
        print(f"\n[{group}]")
        
        # Get subject files
        for session in sessions:
            session_dir = root_dir / group / session
            if not session_dir.exists():
                print(f"  {session}: Directory not found")
                continue
                
            set_files = list(session_dir.glob("*.set"))
            if not set_files:
                print(f"  {session}: No .set files found")
                continue
            
            # Load first subject
            first_file = set_files[0]
            print(f"  {session}: Loading {first_file.name}")
            
            try:
                raw = loader.load_set_file(first_file, resample_rate=256)
                
                if raw is None:
                    print(f"    ✗ Failed to load")
                    continue
                
                # Get basic info
                data = raw.get_data()
                print(f"    ✓ Loaded successfully")
                print(f"      Channels: {data.shape[0]}")
                print(f"      Samples: {data.shape[1]}")
                print(f"      Duration: {data.shape[1] / raw.info['sfreq']:.2f} s")
                print(f"      Sampling rate: {raw.info['sfreq']} Hz")
                
                # Check data values
                print(f"      Data range: [{np.min(data):.2e}, {np.max(data):.2e}]")
                print(f"      Data mean: {np.mean(data):.2e}")
                print(f"      Data std: {np.std(data):.2e}")
                
                # Compute PSD for Alpha band as example
                from mne.time_frequency import psd_array_welch
                psds, freqs = psd_array_welch(
                    data,
                    sfreq=raw.info['sfreq'],
                    fmin=8,
                    fmax=13,
                    n_fft=512,
                    n_overlap=256,
                    verbose=False
                )
                
                alpha_power = np.mean(psds, axis=1)  # Average across frequencies
                print(f"      Alpha power per channel:")
                print(f"        Range: [{np.min(alpha_power):.2e}, {np.max(alpha_power):.2e}]")
                print(f"        Mean: {np.mean(alpha_power):.2e}")
                
            except Exception as e:
                print(f"    ✗ Error: {str(e)}")
    
    print("\n" + "="*80)
    print("DIAGNOSTIC COMPLETE")
    print("="*80)

if __name__ == '__main__':
    check_data_values()
