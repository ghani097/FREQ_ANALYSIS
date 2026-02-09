"""
Configuration settings for EEG Frequency Analysis Tool
"""

# Frequency band definitions (Hz)
FREQUENCY_BANDS = {
    'Delta': (1, 4),
    'Theta': (4, 8),
    'Alpha': (8, 13),
    'Beta': (13, 30),
    'Gamma': (30, 45)
}

# Default analysis parameters
DEFAULT_PARAMS = {
    'resample_rate': 256,  # Hz
    'epoch_length': 2.0,   # seconds
    'freq_range': (1, 45), # Hz
    'n_permutations': 1000,
    'cluster_alpha': 0.05,
    'significance_alpha': 0.05,
    'min_neighbor_chan': 2,
    'tail': 0,  # 0=two-tailed, 1=right, -1=left
    'n_jobs': -1,  # Use all CPUs
    'min_sample_for_permutation': 5  # Fallback to t-tests if n < 5
}

# Visualization settings for publication
PUBLICATION_PARAMS = {
    'figure': {
        'dpi': 300,
        'format': 'png',
        'facecolor': 'white',
        'edgecolor': 'none'
    },
    'font': {
        'family': 'Arial',
        'size': 10,
        'title_size': 14,
        'label_size': 12,
        'legend_size': 10
    },
    'colors': {
        'strong': '#8B0000',      # Dark red for p<0.001
        'moderate': '#FF0000',    # Red for p<0.01
        'significant': '#000000', # Black for p<0.05
        'trend': '#808080',       # Gray for p<0.10
        'cmap': 'jet',           # Jet colormap (classic EEG)
        'sig_marker': '#FF0000'  # Red asterisks for significant channels
    },
    'topomap': {
        'size': 3,
        'contours': 6,
        'sensors': True,
        'names': False,
        'show_names': False
    }
}

# Data validation thresholds
VALIDATION_THRESHOLDS = {
    'min_subjects_per_group': 2,
    'max_bad_channels': 0.2,  # 20% of channels
    'identical_data_threshold': 1e-10,
    'min_data_variance': 1e-15
}

# GUI settings
GUI_SETTINGS = {
    'window_width': 900,
    'window_height': 850,
    'style': 'Fusion',
    'progress_update_interval': 100  # ms
}
