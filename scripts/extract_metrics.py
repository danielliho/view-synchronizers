import sys
import csv
import io
import os

FIELDS = [
    ("avg throughput (view) [without outliers]", "throughput"),
    ("avg latency (view) [without outliers]",    "latency"),
    ("avg handle [without outliers]",            "handle"),
    ("avg view-sync-msgs-per-view [without outliers]", "view_sync_msgs_per_view"),
    ("avg crypto (sign) [without outliers]",     "crypto_sign"),
    ("avg crypto (verif) [without outliers]",    "crypto_verif"),
    ("avg crypto (sign-num) [without outliers]", "crypto_sign_num"),
    ("avg crypto (verif-num) [without outliers]","crypto_verif_num"),
]

def extract(path):
    with open(path, "r") as f:
        lines = f.readlines()

    head = lines[:70]
    label = ""
    for line in head:
        if line.startswith("Starting "):
            label = line[len("Starting "):].strip()
            break

    tail = lines[-50:]
    lookup = {}
    for line in tail:
        if ":" in line:
            key, _, val = line.partition(":")
            lookup[key.strip()] = val.strip()

    row = {}
    for raw_key, col in FIELDS:
        if raw_key not in lookup:
            raise ValueError(f"Key not found in last 50 lines: {raw_key!r}")
        row[col] = lookup[raw_key]

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([label] + [row[col] for _, col in FIELDS])
    print(out.getvalue(), end="")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <input_file_or_dir>", file=sys.stderr)
        sys.exit(1)

    target = sys.argv[1]
    if os.path.isdir(target):
        for name in sorted(os.listdir(target)):
            path = os.path.join(target, name)
            if os.path.isfile(path):
                try:
                    extract(path)
                except Exception as e:
                    print(f"# skipped {name}: {e}", file=sys.stderr)
    else:
        extract(target)
