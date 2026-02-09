"""
Show all available matplotlib markers for significant channels
"""

import matplotlib.pyplot as plt
import numpy as np

# Common marker options
markers = {
    '*': 'Star (5-pointed)',
    'o': 'Circle', 
    's': 'Square',
    'D': 'Diamond',
    '^': 'Triangle up',
    'v': 'Triangle down',
    'P': 'Plus (filled)',
    'X': 'X (filled)',
    '+': 'Plus (thin)',
    'x': 'X (thin)',
    '1': 'Tri down',
    '2': 'Tri up',
    '3': 'Tri left',
    '4': 'Tri right',
    'p': 'Pentagon',
    'h': 'Hexagon',
}

fig, axes = plt.subplots(4, 4, figsize=(14, 12))
axes = axes.flatten()

for idx, (marker, label) in enumerate(markers.items()):
    if idx < len(axes):
        ax = axes[idx]
        
        # Draw marker like it appears on topomap
        ax.scatter([0.5], [0.5], marker=marker, s=800, 
                  c='red', edgecolors='white', linewidths=2)
        
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_title(f"'{marker}' - {label}", fontsize=11, fontweight='bold')
        ax.set_xticks([])
        ax.set_yticks([])
        ax.grid(False)
        
        # Add light background
        ax.set_facecolor('#f0f0f0')

# Hide extra subplots
for idx in range(len(markers), len(axes)):
    axes[idx].axis('off')

plt.suptitle('Matplotlib Marker Options for Significant Channels', 
            fontsize=16, fontweight='bold', y=0.995)
plt.tight_layout()
plt.savefig('all_markers.png', dpi=200, facecolor='white', bbox_inches='tight')
print("✓ Saved: all_markers.png")
print("\nCurrent setting: marker='*' (5-pointed star)")
print("\nWhich marker do you prefer?")
print("  Recommendations:")
print("    '*' = Star (CURRENT - most visible)")
print("    'o' = Circle (clean, classic)")
print("    'D' = Diamond (professional)")
print("    'X' = Filled X (bold)")
print("    '^' = Triangle (directional)")
