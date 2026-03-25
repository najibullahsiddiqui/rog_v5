from __future__ import annotations

import sys
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.ingestion import run_ingestion


def main():
    parser = argparse.ArgumentParser(description="Index approved PDF documents")
    parser.add_argument(
        "--source",
        type=str,
        default="data/source_pdfs",
        help="Folder containing source PDFs",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Compatibility flag. Current pipeline overwrites index files automatically.",
    )
    args = parser.parse_args()

    source_dir = Path(args.source)
    run_ingestion(source_dir)


if __name__ == "__main__":
    main()