from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build" / "pyinstaller"
SPEC_PATH = PROJECT_ROOT / "BetterCode.spec"


def main() -> int:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        str(SPEC_PATH),
    ]

    subprocess.run(command, cwd=PROJECT_ROOT, check=True)

    print("Build finished.")
    if sys.platform == "darwin":
        print(f"App bundle: {DIST_DIR / 'BetterCode.app'}")
    elif sys.platform == "win32":
        print(f"Executable: {DIST_DIR / 'BetterCode' / 'BetterCode.exe'}")
    else:
        print(f"Executable: {DIST_DIR / 'BetterCode' / 'BetterCode'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
