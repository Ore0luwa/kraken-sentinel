"""
utils/cli_check.py — Pre-flight check: is `kraken` CLI installed?

If not found, prints install instructions and exits cleanly.
"""

import shutil
import subprocess
import sys


def check_kraken_cli():
    binary = "kraken"
    path = shutil.which(binary)

    if path is None:
        print()
        print("╔══════════════════════════════════════════════════════════════╗")
        print("║  ERROR: `kraken` CLI not found on PATH                      ║")
        print("╠══════════════════════════════════════════════════════════════╣")
        print("║  Install it with:                                            ║")
        print("║                                                              ║")
        print("║  curl --proto '=https' --tlsv1.2 -LsSf \\                   ║")
        print("║    https://github.com/krakenfx/kraken-cli/releases/         ║")
        print("║    latest/download/kraken-cli-installer.sh | sh             ║")
        print("║                                                              ║")
        print("║  Then re-run: python main.py                                 ║")
        print("╚══════════════════════════════════════════════════════════════╝")
        print()
        sys.exit(1)

    # Get version
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True, text=True, timeout=5
        )
        version = result.stdout.strip() or result.stderr.strip() or "unknown"
    except Exception:
        version = "unknown"

    print(f"✓ Kraken CLI found: {path}  ({version})")
    return path
