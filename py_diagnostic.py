"""
Quick diagnostic script for troubleshooting
Run this before full analysis to check your data
"""

from py_data_loader import EEGDataLoader
from pathlib import Path

def main():
    print("=" * 70)
    print("  EEG DATA DIAGNOSTIC TOOL")
    print("=" * 70)
    print()
    
    # Get root directory
    root_dir = input("Enter path to root data directory: ").strip()
    
    if not root_dir or not Path(root_dir).exists():
        print("❌ Directory not found!")
        return
    
    try:
        loader = EEGDataLoader(root_dir)
        
        # Scan
        print("\n📁 Scanning directory...")
        scan_info = loader.scan_directory()
        
        print(f"✓ Found {scan_info['total_files']} .set files")
        print(f"✓ Groups: {', '.join(scan_info['groups'])}")
        print(f"✓ Sessions: {', '.join(scan_info['sessions'])}")
        
        print("\n📊 Subject counts:")
        for key, subjects in scan_info['subjects'].items():
            print(f"  {key}: {len(subjects)} subjects")
        
        # Check sample sizes
        print("\n📈 Statistical Power Assessment:")
        groups_found = {}
        for key, subjects in scan_info['subjects'].items():
            group_name = key.split('_')[0]
            if group_name not in groups_found:
                groups_found[group_name] = len(subjects)
        
        for group, n_subj in groups_found.items():
            if n_subj >= 10:
                status = "✓ EXCELLENT"
                power = "~90%+"
            elif n_subj >= 5:
                status = "✓ Good"
                power = "~60%+"
            elif n_subj >= 3:
                status = "⚠️ Marginal"
                power = "~20-40%"
            else:
                status = "❌ CRITICAL"
                power = "<10%"
            
            print(f"  {group}: n={n_subj} {status} (Power: {power})")
        
        # Warning for small samples
        min_n = min(groups_found.values()) if groups_found else 0
        if min_n < 5:
            print("\n  ⚠️⚠️⚠️ SAMPLE SIZE WARNING ⚠️⚠️⚠️")
            print(f"  Minimum group size: {min_n} subjects")
            print("  RECOMMENDED: At least 5 subjects per group")
            if min_n < 3:
                print("  CRITICAL: With n<3, statistics are essentially meaningless!")
                print("  P-values will likely be 1 regardless of real differences.")
            print("  Consider collecting more subjects for reliable results.")
        
        # Validate
        print("\n🔍 Validating data loading...")
        validation = loader.validate_data_loading()
        
        if validation['messages']:
            print("\n✓ Messages:")
            for msg in validation['messages']:
                print(f"  {msg}")
        
        if validation['warnings']:
            print("\n⚠️ Warnings:")
            for msg in validation['warnings']:
                print(f"  {msg}")
        
        if validation['errors']:
            print("\n❌ Errors:")
            for msg in validation['errors']:
                print(f"  {msg}")
        
        # Compare groups
        if len(scan_info['groups']) >= 2:
            print("\n🔬 Comparing groups...")
            comparison = loader.compare_groups_data()
            
            if 'error' in comparison:
                print(f"❌ {comparison['error']}")
            else:
                if 'group_a' in comparison:
                    print(f"  Group A: {comparison['group_a']['subject']}")
                    print(f"    Shape: {comparison['group_a']['shape']}")
                    print(f"    Mean: {comparison['group_a']['mean']:.4e}")
                    print(f"    Std: {comparison['group_a']['std']:.4e}")
                
                if 'group_b' in comparison:
                    print(f"  Group B: {comparison['group_b']['subject']}")
                    print(f"    Shape: {comparison['group_b']['shape']}")
                    print(f"    Mean: {comparison['group_b']['mean']:.4e}")
                    print(f"    Std: {comparison['group_b']['std']:.4e}")
                
                if 'comparison' in comparison:
                    comp = comparison['comparison']
                    print(f"\n  Difference Statistics:")
                    print(f"    Max difference: {comp['max_diff']:.4e}")
                    print(f"    Mean difference: {comp['mean_diff']:.4e}")
                    
                    if comp['identical']:
                        print("\n  ⚠️⚠️⚠️ CRITICAL ERROR ⚠️⚠️⚠️")
                        print("  Groups are loading IDENTICAL data!")
                        print("  This WILL cause p-values to be 1.")
                        print("  Check that GroupA and GroupB have different subjects!")
                    else:
                        print("\n  ✓ Groups have different data (GOOD)")
                        print("  Data loading appears correct.")
        
        print("\n" + "=" * 70)
        print("  DIAGNOSTIC COMPLETE")
        print("=" * 70)
        
        if validation['valid'] and not validation['errors']:
            print("\n✓ All checks passed! Ready to run analysis.")
        else:
            print("\n⚠️ Issues found. Fix errors above before running analysis.")
        
    except Exception as e:
        print(f"\n❌ Diagnostic failed: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print()
    input("Press Enter to exit...")


if __name__ == '__main__':
    main()
