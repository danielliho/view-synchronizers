import re
import sys
from pathlib import Path

# Strict pattern
pattern = re.compile(r"^rtt src=\d+ dst=\d+ seq=\d+ us=\d+(\.\d+)?$")

def process_directory(input_dir, output_file, recursive=False):
    input_path = Path(input_dir)

    if not input_path.is_dir():
        print(f"Error: {input_dir} is not a directory")
        sys.exit(1)

    files = input_path.rglob("*") if recursive else input_path.glob("*")

    with open(output_file, "w") as outfile:
        for file in files:
            if file.is_file():
                try:
                    with open(file, "r") as infile:
                        for line in infile:
                            line = line.strip()
                            if pattern.match(line):
                                outfile.write(line + "\n")
                except Exception as e:
                    # Skip binary or unreadable files
                    print(f"Skipping {file}: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python script.py <input_directory> <output_file> [--recursive]")
        sys.exit(1)

    input_dir = sys.argv[1]
    output_file = sys.argv[2]
    recursive = "--recursive" in sys.argv

    process_directory(input_dir, output_file, recursive)