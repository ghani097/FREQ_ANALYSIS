"""
Data loading and validation module for EEGLAB .set files
"""

import os
import numpy as np
import mne
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import warnings

from py_config import VALIDATION_THRESHOLDS


class EEGDataLoader:
    """Load and validate EEGLAB .set files for frequency analysis"""
    
    def __init__(self, root_dir: str):
        self.root_dir = Path(root_dir)
        self.groups = []
        self.sessions = []
        self.subjects = {}
        
    def scan_directory(self) -> Dict:
        """Scan root directory for groups and sessions"""
        
        # Find group folders
        self.groups = [d.name for d in self.root_dir.iterdir() 
                      if d.is_dir() and not d.name.startswith('.') 
                      and d.name.lower() != 'results']
        
        if not self.groups:
            raise ValueError(f"No group folders found in {self.root_dir}")
        
        # Find sessions from first group
        first_group = self.root_dir / self.groups[0]
        self.sessions = [d.name for d in first_group.iterdir() 
                        if d.is_dir() and not d.name.startswith('.')]
        
        if not self.sessions:
            raise ValueError(f"No session folders found in {first_group}")
        
        # Scan for .set files
        self.subjects = {}
        total_files = 0
        
        for group in self.groups:
            for session in self.sessions:
                session_path = self.root_dir / group / session
                if not session_path.exists():
                    continue
                
                # Find .set files
                set_files = list(session_path.glob('*.set'))
                subjects = [f.stem for f in set_files]
                
                key = f"{group}_{session}"
                self.subjects[key] = subjects
                total_files += len(subjects)
        
        return {
            'groups': self.groups,
            'sessions': self.sessions,
            'subjects': self.subjects,
            'total_files': total_files
        }
    
    def get_matched_subjects(self, group: str, session1: str, session2: str) -> List[str]:
        """Get subjects that exist in both sessions"""
        key1 = f"{group}_{session1}"
        key2 = f"{group}_{session2}"
        
        subjects1 = set(self.subjects.get(key1, []))
        subjects2 = set(self.subjects.get(key2, []))
        
        matched = sorted(list(subjects1 & subjects2))
        return matched
    
    def load_set_file(self, filepath: Path, resample_rate: int = None) -> mne.io.Raw:
        """Load EEGLAB .set file and return MNE Raw object"""
        
        # Load with MNE
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=RuntimeWarning)
            raw = mne.io.read_raw_eeglab(filepath, preload=True, verbose=False)
        
        # Standardize channel names
        raw.rename_channels(lambda x: x.upper().strip())
        
        # Resample if needed
        if resample_rate and raw.info['sfreq'] != resample_rate:
            raw.resample(resample_rate, verbose=False)
        
        return raw
    
    def validate_data_loading(self) -> Dict:
        """Validate that data is loading correctly and groups differ"""
        
        results = {
            'valid': True,
            'messages': [],
            'warnings': [],
            'errors': []
        }
        
        # Check minimum subjects
        min_subj = VALIDATION_THRESHOLDS['min_subjects_per_group']
        for key, subjects in self.subjects.items():
            if len(subjects) < min_subj:
                results['warnings'].append(
                    f"{key}: Only {len(subjects)} subjects (need {min_subj}+)"
                )
        
        # Check if groups have different subjects
        if len(self.groups) >= 2:
            group1_subjs = set()
            group2_subjs = set()
            
            for session in self.sessions[:1]:  # Check first session
                key1 = f"{self.groups[0]}_{session}"
                key2 = f"{self.groups[1]}_{session}"
                group1_subjs.update(self.subjects.get(key1, []))
                group2_subjs.update(self.subjects.get(key2, []))
            
            if group1_subjs == group2_subjs:
                results['errors'].append(
                    "⚠️ CRITICAL: Groups have IDENTICAL subject IDs!"
                )
                results['valid'] = False
        
        # Try loading sample data
        try:
            sample_file = self._get_sample_file()
            if sample_file:
                raw = self.load_set_file(sample_file)
                results['messages'].append(
                    f"✓ Successfully loaded sample: {raw.info['nchan']} channels, "
                    f"{raw.info['sfreq']} Hz"
                )
        except Exception as e:
            results['errors'].append(f"Failed to load sample file: {str(e)}")
            results['valid'] = False
        
        return results
    
    def _get_sample_file(self) -> Optional[Path]:
        """Get a sample .set file for testing"""
        for group in self.groups:
            for session in self.sessions:
                session_path = self.root_dir / group / session
                set_files = list(session_path.glob('*.set'))
                if set_files:
                    return set_files[0]
        return None
    
    def compare_groups_data(self) -> Dict:
        """Load sample data from each group and compare"""
        
        if len(self.groups) < 2:
            return {'error': 'Need at least 2 groups for comparison'}
        
        results = {}
        
        try:
            # Load one subject from each group (first session)
            session = self.sessions[0]
            
            # Group A
            key_a = f"{self.groups[0]}_{session}"
            subjects_a = self.subjects.get(key_a, [])
            if not subjects_a:
                return {'error': f'No subjects in {key_a}'}
            
            file_a = self.root_dir / self.groups[0] / session / f"{subjects_a[0]}.set"
            raw_a = self.load_set_file(file_a)
            data_a = raw_a.get_data()
            
            # Group B
            key_b = f"{self.groups[1]}_{session}"
            subjects_b = self.subjects.get(key_b, [])
            if not subjects_b:
                return {'error': f'No subjects in {key_b}'}
            
            file_b = self.root_dir / self.groups[1] / session / f"{subjects_b[0]}.set"
            raw_b = self.load_set_file(file_b)
            data_b = raw_b.get_data()
            
            # Compare
            results['group_a'] = {
                'subject': subjects_a[0],
                'shape': data_a.shape,
                'mean': float(np.mean(data_a)),
                'std': float(np.std(data_a)),
                'min': float(np.min(data_a)),
                'max': float(np.max(data_a))
            }
            
            results['group_b'] = {
                'subject': subjects_b[0],
                'shape': data_b.shape,
                'mean': float(np.mean(data_b)),
                'std': float(np.std(data_b)),
                'min': float(np.min(data_b)),
                'max': float(np.max(data_b))
            }
            
            # Check if identical
            if data_a.shape == data_b.shape:
                max_diff = float(np.max(np.abs(data_a - data_b)))
                mean_diff = float(np.mean(np.abs(data_a - data_b)))
                
                results['comparison'] = {
                    'max_diff': max_diff,
                    'mean_diff': mean_diff,
                    'identical': max_diff < VALIDATION_THRESHOLDS['identical_data_threshold']
                }
                
                if results['comparison']['identical']:
                    results['error'] = "⚠️ CRITICAL: Groups are loading IDENTICAL data!"
                else:
                    results['message'] = "✓ Groups have different data (GOOD)"
            else:
                results['message'] = "✓ Groups have different dimensions (GOOD)"
            
        except Exception as e:
            results['error'] = f"Failed to compare groups: {str(e)}"
        
        return results
