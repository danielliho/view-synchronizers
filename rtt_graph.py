#!/usr/bin/env python3
"""
rtt_graph.py — Parse an RTT log file and render a directed graph
of average round-trip times between nodes.

Usage:
    python rtt_graph.py <logfile> [--out rtt_graph.png]

The script reads lines of the form:
    rtt src=X dst=Y seq=Z us=W.W
and produces a directed graph where each edge's weight is the
average RTT (in µs) over all sequence numbers for that src→dst pair.
Edge colour and width encode latency on a log scale so both
sub-millisecond and hundred-millisecond links stay readable.
"""

import re
import sys
import math
import argparse
from collections import defaultdict
from pathlib import Path
from typing import Dict, Tuple, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import networkx as nx
import numpy as np


# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="RTT log → directed graph")
    p.add_argument("logfile", help="Path to the RTT log file")
    p.add_argument("--out", default="rtt_graph.png",
                   help="Output image path (default: rtt_graph.png)")
    p.add_argument("--unit", choices=["us", "ms"], default="ms",
                   help="Display unit for edge labels (default: ms)")
    p.add_argument("--no-labels", action="store_true",
                   help="Omit numeric latency labels on edges")
    return p.parse_args()


# ── Parsing ───────────────────────────────────────────────────────────────────

RTT_RE = re.compile(
    r"rtt\s+src=(\d+)\s+dst=(\d+)\s+seq=\d+\s+us=([\d.]+)"
)

def parse_rtt_log(path: str) -> Dict[Tuple[int, int], List[float]]:
    """Return {(src, dst): [rtt_us, ...]} from the log."""
    samples: Dict[Tuple[int, int], List[float]] = defaultdict(list)
    with open(path) as fh:
        for line in fh:
            m = RTT_RE.search(line)
            if m:
                src, dst, us = int(m[1]), int(m[2]), float(m[3])
                samples[(src, dst)].append(us)
    return samples


# ── Graph construction ────────────────────────────────────────────────────────

def build_graph(samples: dict) -> nx.DiGraph:
    G = nx.DiGraph()
    for (src, dst), values in samples.items():
        avg_us = sum(values) / len(values)
        G.add_edge(src, dst, avg_us=avg_us, n=len(values))
    return G


# ── Layout ────────────────────────────────────────────────────────────────────

def circular_layout(G: nx.DiGraph) -> dict:
    """Nodes in sorted order around a circle."""
    nodes = sorted(G.nodes())
    n = len(nodes)
    angles = [2 * math.pi * i / n for i in range(n)]
    return {node: (math.cos(a), math.sin(a)) for node, a in zip(nodes, angles)}


# ── Colour mapping ────────────────────────────────────────────────────────────

def latency_colormap():
    """Blue (fast) → yellow → red (slow), perceptually uniform."""
    return plt.cm.plasma


def edge_colours_and_widths(G: nx.DiGraph, edges):
    """Map log(avg_us) → colour and width for each edge."""
    latencies = [G[u][v]["avg_us"] for u, v in edges]
    log_lat   = [math.log10(max(l, 1)) for l in latencies]
    lo, hi    = min(log_lat), max(log_lat)
    span      = hi - lo if hi != lo else 1.0

    cmap      = latency_colormap()
    norm_vals = [(v - lo) / span for v in log_lat]
    colours   = [cmap(n) for n in norm_vals]

    # Width 0.5 (fast) → 3.5 (slow)
    widths    = [0.5 + 3.0 * n for n in norm_vals]
    return colours, widths, latencies, lo, hi


# ── Drawing ───────────────────────────────────────────────────────────────────

def draw_graph(G: nx.DiGraph, args):
    n_nodes = G.number_of_nodes()
    fig_size = max(14, n_nodes * 1.2)
    fig, ax = plt.subplots(figsize=(fig_size, fig_size))
    ax.set_aspect("equal")
    ax.axis("off")

    pos    = circular_layout(G)
    edges  = list(G.edges())
    colours, widths, latencies, log_lo, log_hi = edge_colours_and_widths(G, edges)

    # ── Draw edges ────────────────────────────────────────────────────────────
    # networkx draws curved arrows for DiGraph when connectionstyle is set
    for (u, v), col, w in zip(edges, colours, widths):
        nx.draw_networkx_edges(
            G, pos,
            edgelist=[(u, v)],
            edge_color=[col],
            width=w,
            arrows=True,
            arrowstyle="-|>",
            arrowsize=18,
            connectionstyle="arc3,rad=0.18",
            ax=ax,
            min_source_margin=22,
            min_target_margin=22,
        )

    # ── Edge labels ──────────────────────────────────────────────────────────
    if not args.no_labels:
        edge_labels = {}
        for (u, v), lat_us in zip(edges, latencies):
            if args.unit == "ms":
                edge_labels[(u, v)] = f"{lat_us/1000:.2f} ms"
            else:
                edge_labels[(u, v)] = f"{lat_us:.0f} µs"

        nx.draw_networkx_edge_labels(
            G, pos,
            edge_labels=edge_labels,
            font_size=6,
            label_pos=0.35,
            bbox=dict(boxstyle="round,pad=0.15", fc="white", alpha=0.65, lw=0),
            ax=ax,
        )

    # ── Draw nodes ────────────────────────────────────────────────────────────
    nx.draw_networkx_nodes(
        G, pos,
        node_size=900,
        node_color="#2c3e50",
        ax=ax,
    )
    nx.draw_networkx_labels(
        G, pos,
        font_color="white",
        font_size=11,
        font_weight="bold",
        ax=ax,
    )

    # ── Colour-bar legend ─────────────────────────────────────────────────────
    cmap    = latency_colormap()
    sm      = plt.cm.ScalarMappable(
        cmap=cmap,
        norm=mcolors.Normalize(vmin=log_lo, vmax=log_hi)
    )
    sm.set_array([])
    cb = fig.colorbar(sm, ax=ax, fraction=0.025, pad=0.02, aspect=30)
    cb.set_label("log₁₀(avg RTT µs)", fontsize=12)

    tick_us   = [10**v for v in np.linspace(log_lo, log_hi, 6)]
    tick_vals = [math.log10(t) for t in tick_us]
    if args.unit == "ms":
        tick_strs = [f"{t/1000:.3g} ms" for t in tick_us]
    else:
        tick_strs = [f"{t:.0f} µs" for t in tick_us]
    cb.set_ticks(tick_vals)
    cb.set_ticklabels(tick_strs)

    # ── Title ─────────────────────────────────────────────────────────────────
    ax.set_title(
        f"RTT Directed Graph — {n_nodes} nodes, {G.number_of_edges()} directed links\n"
        f"Edge colour & width = log-scale avg RTT  (blue=fast, red=slow)",
        fontsize=13, pad=16,
    )

    plt.tight_layout()
    out = args.out
    plt.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Saved → {out}")
    plt.close(fig)


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary(G: nx.DiGraph, unit: str):
    print(f"\n{'─'*56}")
    print(f"  {'src→dst':<12} {'avg RTT':>12}  {'samples':>8}")
    print(f"{'─'*56}")
    factor = 1000 if unit == "ms" else 1
    suffix = "ms" if unit == "ms" else "µs"
    for u, v, d in sorted(G.edges(data=True), key=lambda e: e[2]["avg_us"]):
        avg = d["avg_us"] / factor
        print(f"  {u:>4} → {v:<4}  {avg:>10.3f} {suffix}   {d['n']:>6} samples")
    print(f"{'─'*56}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args    = parse_args()
    path    = args.logfile

    if not Path(path).exists():
        sys.exit(f"Error: file not found: {path}")

    print(f"Parsing {path} …")
    samples = parse_rtt_log(path)

    if not samples:
        sys.exit("No RTT entries found. Check the log format.")

    G = build_graph(samples)
    print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} directed edges")

    print_summary(G, args.unit)
    draw_graph(G, args)


if __name__ == "__main__":
    main()
