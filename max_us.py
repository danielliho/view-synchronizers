#!/usr/bin/env python3
"""Print the largest value that appears as us=<number> in a text file."""

import argparse
import re
import sys
from pathlib import Path

US_PATTERN = re.compile(r"\bus=([+-]?\d+(?:\.\d+)?)\b")


def find_max_us(file_path: Path) -> float:
    max_us = None

    with file_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            for match in US_PATTERN.finditer(line):
                value = float(match.group(1))
                if max_us is None or value > max_us:
                    max_us = value

    if max_us is None:
        raise ValueError("No us= values found")

    return max_us


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read a log file and output the biggest us= number.",
    )
    parser.add_argument("file", type=Path, help="Path to input file")
    args = parser.parse_args()

    if not args.file.is_file():
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return 1

    try:
        max_us = find_max_us(args.file)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(max_us)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
