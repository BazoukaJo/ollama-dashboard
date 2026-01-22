"""Install dependencies."""

import subprocess
import sys

print("\n" + "=" * 70)
print("INSTALLING DEPENDENCIES")
print("=" * 70 + "\n")

# Read requirements
try:
    with open('requirements.txt', 'r') as f:
        requirements = f.read()
    print("Requirements to install:")
    for line in requirements.strip().split('\n'):
        if line and not line.startswith('#'):
            print(f"  - {line}")
    print()
except FileNotFoundError:
    print("❌ requirements.txt not found\n")
    sys.exit(1)

# Install
print("Installing...")
result = subprocess.run(
    [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
    capture_output=False
)

if result.returncode == 0:
    print("\n" + "=" * 70)
    print("✅ DEPENDENCIES INSTALLED")
    print("=" * 70)
    print("\nNow run: python start.py\n")
else:
    print("\n❌ Installation failed\n")
    sys.exit(1)
