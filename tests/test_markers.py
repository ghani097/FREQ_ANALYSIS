"""
Test different marker styles to see star vs asterisk
"""

import matplotlib.pyplot as plt
import numpy as np

fig, axes = plt.subplots(1, 3, figsize=(12, 4))

# Test 1: '*' marker (star)
ax = axes[0]
x, y = [1, 2, 3], [1, 2, 3]
ax.scatter(x, y, marker='*', s=500, c='red', edgecolors='white', linewidths=2)
ax.set_title("marker='*' (STAR - 5 pointed)", fontsize=12, fontweight='bold')
ax.set_xlim(0, 4)
ax.set_ylim(0, 4)
ax.grid(True, alpha=0.3)

# Test 2: 'x' marker (cross/X)
ax = axes[1]
ax.scatter(x, y, marker='x', s=500, c='red', linewidths=3)
ax.set_title("marker='x' (X/Cross)", fontsize=12, fontweight='bold')
ax.set_xlim(0, 4)
ax.set_ylim(0, 4)
ax.grid(True, alpha=0.3)

# Test 3: '+' marker (plus)
ax = axes[2]
ax.scatter(x, y, marker='+', s=500, c='red', linewidths=3)
ax.set_title("marker='+' (Plus)", fontsize=12, fontweight='bold')
ax.set_xlim(0, 4)
ax.set_ylim(0, 4)
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('marker_test.png', dpi=150, facecolor='white')
print("Saved marker_test.png")
print("\nIn matplotlib:")
print("  '*' = STAR (5-pointed star shape)")
print("  'x' = X or cross")
print("  '+' = Plus sign")
print("\nThere is NO true 'asterisk' marker (*) in matplotlib")
print("The '*' marker draws a star, not an asterisk symbol")
