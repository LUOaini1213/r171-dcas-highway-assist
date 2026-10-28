"""Check that vendor/p7_dms is an unmodified copy of the P7 DMS files (SHA-256; byte comparison if P7 exists).

Run:  python -X utf8 -I scripts/check_vendor.py      (exit code 1 on any difference)
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "p7_dms"
P7 = ROOT.parent / "P7_座舱DMS与分心预警" / "dms"
EXPECTED = {
    "__init__.py": "6d21590fa2dd5315949bf250850d21eebe3bdc91d3576e65ae86340715da13d6",
    "labels.py": "28d91b485bc5292769ecd06c171394c52407948b4350333f5f8a1b4895d9c8e4",
    "regulations.py": "0425973aeec9dbd1e524cc1d1e947b20ba448b2dd01c9a2b2110529136198504",
    "config.py": "ac055e13517fee219f8e4544375642b9a4329d575c9aa7f5ba1b3fa333b1cf27",
    "detectors.py": "3ce216b8c53c91144d379430409663992a9adb62f50bec05891b1d39a5f3df0b",
}


def main() -> int:
    bad = []
    for name, h in EXPECTED.items():
        data = (VENDOR / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != h:
            bad.append(f"{name}: SHA-256 differs from SOURCE.md")
        if P7.exists() and (P7 / name).exists() and (P7 / name).read_bytes() != data:
            bad.append(f"{name}: differs from the P7 original")
    print("vendor/p7_dms:", "OK (identical to P7)" if not bad else "; ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
