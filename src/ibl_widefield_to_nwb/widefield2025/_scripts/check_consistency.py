#!/usr/bin/env python3
"""
CLI wrapper for widefield NWB consistency checks.

Imports all check logic from the library module:
  ibl_widefield_to_nwb.widefield2025.testing._consistency_checks

Usage
-----
    python _scripts/check_consistency.py --raw /path/to/raw.nwb
    python _scripts/check_consistency.py --processed /path/to/processed.nwb
    python _scripts/check_consistency.py --raw /path/to/raw.nwb --processed /path/to/processed.nwb
"""

import argparse
import logging
import sys
from pathlib import Path

from one.api import ONE

from ibl_widefield_to_nwb.widefield2025.testing._consistency_checks import (
    check_nwbfile_for_consistency,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

ONE_KWARGS = dict(base_url="https://openalyx.internationalbrainlab.org", password="international")


def main():
    parser = argparse.ArgumentParser(description="Validate IBL widefield NWB files against ONE source data.")
    parser.add_argument("--raw", type=Path, help="Path to raw NWB file")
    parser.add_argument("--processed", type=Path, help="Path to processed NWB file")
    args = parser.parse_args()

    if not args.raw and not args.processed:
        parser.error("Provide at least one of --raw or --processed")

    one = ONE(**ONE_KWARGS)
    all_passed = True

    for path in filter(None, [args.raw, args.processed]):
        if not path.exists():
            logging.error(f"File not found: {path}")
            all_passed = False
            continue
        passed = check_nwbfile_for_consistency(one=one, nwbfile_path=path)
        all_passed = all_passed and passed

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
