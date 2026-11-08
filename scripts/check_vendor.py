"""Check that vendor/p7_dms is an unmodified copy of the DMS files from
https://github.com/LUOaini1213/dms-distraction-warning-tests (commit 39a022d, folder dms/).

Always checks the SHA-256 values recorded below (and in vendor/p7_dms/SOURCE.md).  If a checkout of that
repository is given with --p7 <dir>, the files are also compared byte for byte with <dir>/dms/.

Run:  python -X utf8 -I scripts/check_vendor.py [--p7 <dms-distraction-warning-tests checkout>]
      (exit code 1 on any difference)
"""
import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "p7_dms"
EXPECTED = {
    "__init__.py": "6d21590fa2dd5315949bf250850d21eebe3bdc91d3576e65ae86340715da13d6",
    "labels.py": "28d91b485bc5292769ecd06c171394c52407948b4350333f5f8a1b4895d9c8e4",
    "regulations.py": "0425973aeec9dbd1e524cc1d1e947b20ba448b2dd01c9a2b2110529136198504",
    "config.py": "ac055e13517fee219f8e4544375642b9a4329d575c9aa7f5ba1b3fa333b1cf27",
    "detectors.py": "3ce216b8c53c91144d379430409663992a9adb62f50bec05891b1d39a5f3df0b",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p7", help="checkout of dms-distraction-warning-tests for a byte comparison")
    a = ap.parse_args()
    p7 = Path(a.p7) / "dms" if a.p7 else None
    if p7 is not None and not p7.is_dir():
        print(f"vendor/p7_dms: --p7 given but {p7} is not a directory")
        return 1
    bad = []
    for name, h in EXPECTED.items():
        data = (VENDOR / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != h:
            bad.append(f"{name}: SHA-256 differs from SOURCE.md")
        if p7 is not None and (not (p7 / name).exists() or (p7 / name).read_bytes() != data):
            bad.append(f"{name}: differs from the P7 original")
    if bad:
        print("vendor/p7_dms:", "; ".join(bad))
    elif p7 is not None:
        print("vendor/p7_dms: OK (hashes match and files are byte-identical to the P7 checkout)")
    else:
        print("vendor/p7_dms: hashes OK (no P7 checkout given with --p7, byte comparison skipped)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
