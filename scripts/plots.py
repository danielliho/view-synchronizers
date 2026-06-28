#!/usr/bin/env python3
import argparse
import re
from io import StringIO
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import pandas as pd
import seaborn as sns


DEFAULT_N_VALUES = [5, 11, 21, 31, 41]


def parse_block_csv(csv_path: Path, n_values):
    text = csv_path.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # separator lines like ",,,,,,,,"
    sep_re = re.compile(r"^,(\s*,)*$")
    blocks, current = [], []

    for ln in lines:
        if sep_re.match(ln):
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(ln)
    if current:
        blocks.append(current)

    if len(blocks) != len(n_values):
        raise ValueError(
            f"Found {len(blocks)} blocks but got {len(n_values)} n-values.\n"
            f"Use --n-values with exactly {len(blocks)} values."
        )

    frames = []
    for i, block_lines in enumerate(blocks):
        block_csv = "\n".join(block_lines)
        df_block = pd.read_csv(StringIO(block_csv))
        if "metric" not in df_block.columns:
            raise ValueError(f"Block {i+1} missing 'metric' column/header.")
        df_block = df_block.rename(columns={"metric": "algorithm"})
        df_block["n"] = n_values[i]
        frames.append(df_block)

    df = pd.concat(frames, ignore_index=True)

    metric_cols = [c for c in df.columns if c not in ("algorithm", "n")]
    for c in metric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Keep algorithm order as first appearance in source
    algo_order = list(dict.fromkeys(df["algorithm"].astype(str).tolist()))
    df["algorithm"] = pd.Categorical(df["algorithm"], categories=algo_order, ordered=True)

    return df, metric_cols, algo_order


def safe_name(name: str) -> str:
    return (
        name.strip()
        .replace(" ", "_")
        .replace("(", "")
        .replace(")", "")
        .replace("-", "_")
        .replace("/", "_")
    )


def make_palette(algorithms):
    # dynamic colors based on how many algorithms are present
    colors = sns.color_palette("tab10", n_colors=max(3, len(algorithms)))
    return {alg: colors[i] for i, alg in enumerate(algorithms)}


def plot_metric(df, metric, algo_order, palette, out_file: Path):
    n_ticks = sorted(df["n"].dropna().unique().tolist())

    plt.figure(figsize=(8.8, 5.3))
    ax = plt.gca()
    sns.lineplot(
        data=df,
        x="n",
        y=metric,
        hue="algorithm",
        hue_order=algo_order,
        palette=palette,
        marker="o",
        linewidth=2.2,
        markersize=7,
        ax=ax,
    )
    ax.set_xlabel("n")
    ax.set_ylabel(metric)
    ax.set_xticks(n_ticks)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=7, min_n_ticks=5))
    ax.grid(True, linestyle="--", alpha=0.25)
    plt.tight_layout()
    plt.savefig(out_file, dpi=220)
    plt.close()


def plot_key_metrics_aggregate(df, algo_order, palette, out_file: Path):
    key_metrics = ["Latency (ms)", "Throughput (Kops/s)", "View sync messages"]
    available_metrics = [m for m in key_metrics if m in df.columns]

    if not available_metrics:
        print("[skip] aggregate plot: none of the key metrics were found")
        return

    n_ticks = sorted(df["n"].dropna().unique().tolist())
    # Taller-than-wide layout keeps stacked panels readable.
    fig, axes = plt.subplots(len(available_metrics), 1, figsize=(6.6, 10.2), sharex=True)
    if len(available_metrics) == 1:
        axes = [axes]

    for ax, metric in zip(axes, available_metrics):
        sns.lineplot(
            data=df,
            x="n",
            y=metric,
            hue="algorithm",
            hue_order=algo_order,
            palette=palette,
            marker="o",
            linewidth=2.2,
            markersize=6,
            ax=ax,
            legend=(ax is axes[0]),
        )
        ax.set_ylabel(metric)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=7, min_n_ticks=5))
        ax.grid(True, linestyle="--", alpha=0.25)

    axes[-1].set_xlabel("n")
    axes[-1].set_xticks(n_ticks)

    axes[0].legend(labelspacing=0.25, loc="upper left", fontsize="14")


    fig.tight_layout()
    fig.savefig(out_file, dpi=240)
    plt.close(fig)
    print(f"[saved] {out_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Plot repeated-block CSV (algorithms from source, blocks mapped to n-values)."
    )
    parser.add_argument("csv_file", type=Path, help="Input CSV path")
    parser.add_argument(
        "--n-values",
        type=float,
        nargs="+",
        default=DEFAULT_N_VALUES,
        help=f"Block n-values top->bottom (default: {DEFAULT_N_VALUES})",
    )
    parser.add_argument("--outdir", type=Path, default=Path("plots"), help="Output directory")
    args = parser.parse_args()

    if not args.csv_file.exists():
        raise FileNotFoundError(f"CSV not found: {args.csv_file}")

    args.outdir.mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid", context="talk")

    df, metric_cols, algo_order = parse_block_csv(args.csv_file, args.n_values)
    palette = make_palette(algo_order)

    print(f"[ok] file: {args.csv_file}")
    print(f"[ok] algorithms ({len(algo_order)}): {algo_order}")
    print(f"[ok] n-values: {args.n_values}")
    print(f"[ok] metrics: {metric_cols}")

    for metric in metric_cols:
        out = args.outdir / f"plot_{safe_name(metric)}.png"
        plot_metric(df, metric, algo_order, palette, out)
        print(f"[saved] {out}")

    out_agg = args.outdir / "plot_key_metrics_aggregate.png"
    plot_key_metrics_aggregate(df, algo_order, palette, out_agg)


if __name__ == "__main__":
    main()