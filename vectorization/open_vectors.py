import sys
import numpy as np

path = sys.argv[1] if len(sys.argv) > 1 else "output/backend1.vectors.npz"
data = np.load(path)

print("Sections:", data.files)
for section in data.files:
    vec = data[section]
    print(f"\n{section}: shape={vec.shape}, length={np.linalg.norm(vec):.3f}")
    print(vec)                                    # all 384 numbers