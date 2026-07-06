#!/usr/bin/env python3
import argparse
import ast
import csv
import math
import os
import re
from typing import Dict, List, Optional, Set

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

BLOCK_RE = re.compile(
    r"^<{8,}\s+protocol=([^\s]+).*;#faults=([^\s]+).*;#joiners=([^\s]+).*;#repeats=([^\s]+)"
)
REPEAT_RE = re.compile(r"^>{8,}.*;repeat=(\d+)")
OUTLIER_RE = re.compile(r"^outlier runs for protocol\s+([^:]+):\s*(\[.*\])\s*$")
ABORTED_RE = re.compile(r"^------ reached cutoff bound ------$")

METRIC_LINE_PATTERNS = {
    "throughput(view)": re.compile(r"^throughput-view:\s*([-+eE0-9\.]+)\s+out of\s+\d+\s*$"),
    "latency(view)": re.compile(r"^latency-view:\s*([-+eE0-9\.]+)\s+out of\s+\d+\s*$"),
    "handle": re.compile(r"^handle:\s*([-+eE0-9\.]+)\s+out of\s+\d+\s*$"),
    "timeouts": re.compile(r"^timeouts:\s*([-+eE0-9\.]+)\s+out of\s+\d+\s*$"),
    "view-sync-msgs-per-view": re.compile(r"^view-sync-msgs-per-view:\s*([-+eE0-9\.]+)\s+out of\s+\d+\s*$"),
    "crypto(sign)": re.compile(r"^crypto-sign:\s*([-+eE0-9\.]+)\s+out of\s+\d+\s*$"),
    "crypto(verif)": re.compile(r"^crypto-verif:\s*([-+eE0-9\.]+)\s+out of\s+\d+\s*$"),
    "crypto(sign-num)": re.compile(r"^crypto-num-sign:\s*([-+eE0-9\.]+)\s+out of\s+\d+\s*$"),
    "crypto(verif-num)": re.compile(r"^crypto-num-verif:\s*([-+eE0-9\.]+)\s+out of\s+\d+\s*$"),
}

EPS_FLAT = 1e-12


class RepeatRun:
    def __init__(self, repeat: int):
        self.repeat = repeat
        self.metrics: Dict[str, float] = {}
        self.aborted = False


class Block:
    def __init__(self, protocol: str, faults: str, joiners: str, repeats_expected: str):
        self.protocol = protocol
        self.faults = faults
        self.joiners = joiners
        self.repeats_expected = repeats_expected
        self.runs: Dict[int, RepeatRun] = {}
        self.printed_outliers: Optional[Set[int]] = None



def strip_ansi(line: str) -> str:
    return ANSI_RE.sub("", line).strip()


def extract_algorithm_name(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = strip_ansi(raw)
            if line.startswith("Starting "):
                return line[len("Starting "):].strip()
    return os.path.basename(path)


def collect_input_files(path: str) -> List[str]:
    if os.path.isdir(path):
        files = []
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            if os.path.isfile(full):
                files.append(full)
        return files
    return [path]



def percentile(sorted_vals: List[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = (len(sorted_vals) - 1) * p
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_vals[lo]
    frac = idx - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac



def outlier_run_ids(values: List[float], run_ids: List[int], ratio: float = 10.0) -> Set[int]:
    # Keep this identical to experiments.py.
    if len(values) < 4:
        return set()
    sorted_vals = sorted(values)
    median = percentile(sorted_vals, 0.5)
    if median <= 0:
        return set()
    low = median / ratio
    high = median * ratio
    out = set()
    for idx, val in enumerate(values):
        if val < low or val > high:
            out.add(run_ids[idx])
    return out



def parse_aborted_runs_list(line: str) -> Set[int]:
    # Format in logs: aborted runs so far: [(<Protocol.ONEP: 'BASIC_ONEP'>, 20, 3), ...]
    # We avoid brittle parsing of Protocol enum repr; only extract the final tuple integer.
    if not line.startswith("aborted runs so far:"):
        return set()
    out = set()
    for m in re.finditer(r",\s*(-?\d+)\)", line):
        out.add(int(m.group(1)))
    return out



def parse_log(path: str) -> List[Block]:
    blocks: List[Block] = []
    current_block: Optional[Block] = None
    current_repeat: Optional[int] = None

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = strip_ansi(raw)
            if not line:
                continue

            m_block = BLOCK_RE.match(line)
            if m_block:
                current_block = Block(
                    protocol=m_block.group(1),
                    faults=m_block.group(2),
                    joiners=m_block.group(3),
                    repeats_expected=m_block.group(4),
                )
                blocks.append(current_block)
                current_repeat = None
                continue

            if current_block is None:
                continue

            m_repeat = REPEAT_RE.match(line)
            if m_repeat:
                current_repeat = int(m_repeat.group(1))
                current_block.runs.setdefault(current_repeat, RepeatRun(current_repeat))
                continue

            if ABORTED_RE.match(line) and current_repeat is not None:
                current_block.runs.setdefault(current_repeat, RepeatRun(current_repeat)).aborted = True
                continue

            # Also ingest the running aborted list, because cut-off markers can get truncated.
            aborted_from_list = parse_aborted_runs_list(line)
            for rid in aborted_from_list:
                current_block.runs.setdefault(rid, RepeatRun(rid)).aborted = True

            m_out = OUTLIER_RE.match(line)
            if m_out:
                try:
                    parsed = ast.literal_eval(m_out.group(2))
                    if isinstance(parsed, list):
                        current_block.printed_outliers = {int(x) for x in parsed}
                except Exception:
                    current_block.printed_outliers = None
                continue

            if current_repeat is None:
                continue

            for metric_name, pat in METRIC_LINE_PATTERNS.items():
                mm = pat.match(line)
                if mm:
                    current_block.runs.setdefault(current_repeat, RepeatRun(current_repeat)).metrics[metric_name] = float(mm.group(1))
                    break

    return blocks



def mean(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0



def stddev(vals: List[float], sample: bool) -> float:
    n = len(vals)
    if n == 0:
        return 0.0
    if sample and n < 2:
        return 0.0
    mu = mean(vals)
    sse = sum((x - mu) ** 2 for x in vals)
    denom = (n - 1) if sample else n
    return math.sqrt(sse / denom)


def sanitize_value(v: float, eps: float = EPS_FLAT) -> float:
    return 0.0 if abs(v) < eps else v


def format_mean_std(mean_v: float, std_v: float) -> str:
    return f"{sanitize_value(mean_v):.12g} ({sanitize_value(std_v):.12g})"



def compute_block_stats(block: Block, sample: bool, include_aborted: bool) -> Dict[str, object]:
    core = ["throughput(view)", "latency(view)", "handle"]

    valid_runs: List[int] = []
    for rid, run in sorted(block.runs.items()):
        if run.aborted and (not include_aborted):
            continue
        if any(k not in run.metrics for k in core):
            continue
        if not (run.metrics["throughput(view)"] > 0 and run.metrics["latency(view)"] > 0 and run.metrics["handle"] > 0):
            continue
        valid_runs.append(rid)

    metric_names = list(METRIC_LINE_PATTERNS.keys())

    metric_outliers: Dict[str, Set[int]] = {}
    for metric in metric_names:
        vals = [block.runs[rid].metrics[metric] for rid in valid_runs if metric in block.runs[rid].metrics]
        ids = [rid for rid in valid_runs if metric in block.runs[rid].metrics]
        metric_outliers[metric] = outlier_run_ids(vals, ids)

    all_outliers: Set[int] = set()
    for outs in metric_outliers.values():
        all_outliers.update(outs)

    kept_runs = [rid for rid in valid_runs if rid not in all_outliers]

    stats = {}
    for metric in metric_names:
        vals = [block.runs[rid].metrics[metric] for rid in kept_runs if metric in block.runs[rid].metrics]
        m = sanitize_value(mean(vals))
        s = sanitize_value(stddev(vals, sample=sample))
        stats[metric] = {
            "n": len(vals),
            "mean_without_outliers": m,
            "stddev": s,
        }

    return {
        "protocol": block.protocol,
        "faults": block.faults,
        "joiners": block.joiners,
        "repeats_expected": block.repeats_expected,
        "include_aborted": include_aborted,
        "valid_runs_before_outliers": valid_runs,
        "outlier_runs": sorted(all_outliers),
        "kept_runs": kept_runs,
        "printed_outliers": sorted(block.printed_outliers) if block.printed_outliers is not None else None,
        "metrics": stats,
    }



def print_block(result: Dict[str, object]) -> None:
    print(
        f"protocol={result['protocol']} faults={result['faults']} joiners={result['joiners']} "
        f"repeats={result['repeats_expected']}"
    )
    print(f"  include_aborted: {result['include_aborted']}")
    print(f"  valid runs before outlier filtering: {result['valid_runs_before_outliers']}")
    print(f"  outlier runs (computed): {result['outlier_runs']}")
    if result["printed_outliers"] is not None:
        status = "OK" if result["printed_outliers"] == result["outlier_runs"] else "DIFF"
        print(f"  outlier runs (printed):  {result['printed_outliers']} [{status}]")
    print(f"  kept runs: {result['kept_runs']}")

    for metric, data in result["metrics"].items():
        print(
            f"  {metric}: n={data['n']} "
            f"mean_without_outliers={sanitize_value(data['mean_without_outliers']):.12g} "
            f"stddev={sanitize_value(data['stddev']):.12g}"
        )
    print()


def csv_row_from_result(algorithm: str, result: Dict[str, object]) -> List[object]:
    m = result["metrics"]
    return [
        algorithm,
        format_mean_std(m["throughput(view)"]["mean_without_outliers"], m["throughput(view)"]["stddev"]),
        format_mean_std(m["latency(view)"]["mean_without_outliers"], m["latency(view)"]["stddev"]),
        format_mean_std(m["handle"]["mean_without_outliers"], m["handle"]["stddev"]),
        format_mean_std(m["view-sync-msgs-per-view"]["mean_without_outliers"], m["view-sync-msgs-per-view"]["stddev"]),
        format_mean_std(m["crypto(sign)"]["mean_without_outliers"], m["crypto(sign)"]["stddev"]),
        format_mean_std(m["crypto(verif)"]["mean_without_outliers"], m["crypto(verif)"]["stddev"]),
        format_mean_std(m["crypto(sign-num)"]["mean_without_outliers"], m["crypto(sign-num)"]["stddev"]),
        format_mean_std(m["crypto(verif-num)"]["mean_without_outliers"], m["crypto(verif-num)"]["stddev"]),
    ]


def write_csv(path: str, rows: List[List[object]]) -> None:
    header = [
        "Algorithm",
        "Throughput (Kops/s)",
        "Latency (ms)",
        "Handle (ms)",
        "View sync. mes. (#)",
        "Sign dur. (ms)",
        "Verif. dur. (ms)",
        "Sign num. (#)",
        "Verif. num. (#)",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)



def main() -> int:
    ap = argparse.ArgumentParser(
        description="Compute per-metric stddev from experiment result logs, excluding aborted and outlier runs."
    )
    ap.add_argument("input_path", help="Path to a results log file or a directory of log files")
    ap.add_argument(
        "--population",
        action="store_true",
        help="Use population stddev (N) instead of sample stddev (N-1). Default is sample stddev.",
    )
    ap.add_argument(
        "--protocol",
        default="",
        help="Only report blocks whose protocol exactly matches this value (e.g., BASIC_ONEP).",
    )
    ap.add_argument(
        "--include-aborted",
        action="store_true",
        help="Include aborted runs in stats (default: excluded).",
    )
    ap.add_argument(
        "--csv-output",
        default="",
        help="Write aggregated means (without outliers) to this CSV file.",
    )

    args = ap.parse_args()

    files = collect_input_files(args.input_path)
    if len(files) == 0:
        print("No input files found.")
        return 1

    csv_rows: List[List[object]] = []
    any_printed = False

    for file_path in files:
        blocks = parse_log(file_path)
        if not blocks:
            continue

        algorithm = extract_algorithm_name(file_path)

        for block in blocks:
            if args.protocol and block.protocol != args.protocol:
                continue

            result = compute_block_stats(
                block,
                sample=(not args.population),
                include_aborted=args.include_aborted,
            )
            print_block(result)
            csv_rows.append(csv_row_from_result(algorithm, result))
            any_printed = True

    if not any_printed:
        print("No matching blocks found for the requested filters.")
        return 1

    if args.csv_output:
        write_csv(args.csv_output, csv_rows)
        print("CSV written to:", args.csv_output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
