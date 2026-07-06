#!/usr/bin/env python3
import argparse
import csv
import re
from pathlib import Path
from typing import List, Tuple


HEADER_LINEBREAKS = {
    "Throughput (Kops/s)": ["Throughput", "(Kops/s)"],
    "View sync. mes. (#)": ["View sync.", "mes. (#)"],
}


# ---------- Parsing ----------

def normalize_row(row: List[str]) -> List[str]:
    return [(c or "").strip() for c in row]


def is_blank_row(row: List[str]) -> bool:
    return all(c == "" for c in normalize_row(row))


def is_number_like(s: str) -> bool:
    s = (s or "").strip()
    if s == "":
        return False
    # plain float/int/scientific notation
    return re.fullmatch(r"[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?", s) is not None


def is_mean_std_like(s: str) -> bool:
    s = (s or "").strip()
    # values like: 138.42 (0.90)
    return re.fullmatch(
        r"([+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?)\s*\(\s*([+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?)\s*\)",
        s,
    ) is not None


def likely_header(row: List[str]) -> bool:
    """
    Header heuristic:
    - non-blank
    - at least 2 non-empty cells
    - not mostly numeric
    """
    r = normalize_row(row)
    cells = [c for c in r if c != ""]
    if len(cells) < 2:
        return False
    # Strong signal for this workflow.
    if cells[0].strip().lower() == "algorithm":
        return True

    # Data rows from the stddev exporter look like "mean (stddev)" in most metric cells.
    if len(cells) >= 3:
        tail = cells[1:]
        pair_like = sum(1 for c in tail if is_mean_std_like(c))
        if pair_like >= max(1, int(0.6 * len(tail))):
            return False

    numeric = sum(1 for c in cells if is_number_like(c))
    return numeric < len(cells) / 2


def split_tables(csv_path: Path) -> List[Tuple[List[str], List[List[str]]]]:
    """
    A table is:
      header row + subsequent data rows
    until:
      - blank row, or
      - next likely header row.
    """
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = [normalize_row(r) for r in csv.reader(f)]

    tables: List[Tuple[List[str], List[List[str]]]] = []
    i = 0
    n = len(rows)

    while i < n:
        row = rows[i]
        if is_blank_row(row) or not likely_header(row):
            i += 1
            continue

        header = row
        width = len(header)
        data: List[List[str]] = []
        i += 1

        while i < n:
            r = rows[i]
            if is_blank_row(r):
                i += 1
                break
            if likely_header(r):  # new table starts
                break

            rr = (r + [""] * width)[:width]
            data.append(rr)
            i += 1

        if data:
            tables.append((header, data))

    return tables


# ---------- LaTeX rendering ----------

def latex_escape_text(s: str) -> str:
    repl = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    out = s
    for k, v in repl.items():
        out = out.replace(k, v)
    return out


def format_header_cell(h: str) -> str:
    key = (h or "").strip()
    lines = HEADER_LINEBREAKS.get(key)
    if not lines:
        # Generic split for headers with trailing units, e.g. "Latency (ms)" ->
        # line 1: "Latency", line 2: "(ms)".
        m = re.fullmatch(r"(.+?)\s*(\([^\)]*\))", key)
        if m and key.lower() != "algorithm":
            left = m.group(1).strip()
            unit = m.group(2).strip()
            if left:
                lines = [left, unit]
    if not lines:
        return latex_escape_text(key)
    esc_lines = [latex_escape_text(x) for x in lines]
    return r"\shortstack[c]{" + r" \\ ".join(esc_lines) + "}"


def format_number(s: str) -> str:
    """
    Light cleanup for numeric display:
    - ints as ints
    - floats trimmed (up to 6 decimals)
    """
    s = (s or "").strip()
    if not is_number_like(s):
        return s
    v = float(s)
    if abs(v - round(v)) < 1e-12:
        return str(int(round(v)))
    return f"{v:.3f}".rstrip("0").rstrip(".")


def format_mean_std(s: str) -> str:
    """
    Round mean and stddev in values of the form "mean (stddev)":
    - mean: same formatting policy as standalone numbers (up to 3 decimals)
    - stddev: always rounded to 3 decimals (trim trailing zeros)
    """
    s = (s or "").strip()
    m = re.fullmatch(
        r"([+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?)\s*\(\s*([+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?)\s*\)",
        s,
    )
    if not m:
        return s

    mean_s = m.group(1)
    std_s = m.group(5)
    mean_fmt = format_number(mean_s)
    std_v = float(std_s)
    std_fmt = f"{std_v:.3f}".rstrip("0").rstrip(".")
    if std_fmt == "-0":
        std_fmt = "0"
    return f"{mean_fmt} ({std_fmt})"


def to_siunitx_uncertainty(s: str) -> str:
    """
    Convert "mean (stddev)" into siunitx uncertainty form "mean(stddev)".
    This keeps S-column numeric parsing/alignment active.
    """
    pair = format_mean_std(s)
    m = re.fullmatch(r"(.+)\s*\(\s*(.+)\s*\)", pair)
    if not m:
        return pair
    return f"{m.group(1).strip()}({m.group(2).strip()})"


def detect_numeric_columns(header: List[str], rows: List[List[str]]) -> List[bool]:
    """
    Column 0 defaults to text.
    Others numeric if >=80% of non-empty cells are number-like.
    """
    m = len(header)
    numeric = [False] * m
    for j in range(m):
        if j == 0:
            numeric[j] = False
            continue
        col = [(r[j] if j < len(r) else "").strip() for r in rows]
        nonempty = [x for x in col if x != ""]
        if not nonempty:
            numeric[j] = False
            continue
        num = sum(1 for x in nonempty if is_number_like(x) or is_mean_std_like(x))
        numeric[j] = (num / len(nonempty)) >= 0.8
    return numeric


def detect_pair_columns(header: List[str], rows: List[List[str]]) -> List[bool]:
    """
    Column 0 defaults to text.
    Other columns are pair columns if >=80% of non-empty cells look like "mean (stddev)".
    """
    m = len(header)
    pair = [False] * m
    for j in range(m):
        if j == 0:
            pair[j] = False
            continue
        col = [(r[j] if j < len(r) else "").strip() for r in rows]
        nonempty = [x for x in col if x != ""]
        if not nonempty:
            pair[j] = False
            continue
        num = sum(1 for x in nonempty if is_mean_std_like(x))
        pair[j] = (num / len(nonempty)) >= 0.8
    return pair


def make_colspec(numeric_cols: List[bool], text_align: str = "l") -> str:
    # text columns: l/c/r ; numeric columns: S
    parts = []
    for is_num in numeric_cols:
        parts.append("S" if is_num else text_align)
    return "".join(parts)


def make_colspec_with_pairs(numeric_cols: List[bool], pair_cols: List[bool], text_align: str = "l") -> str:
    parts = []
    for is_num, is_pair in zip(numeric_cols, pair_cols):
        if is_pair:
            # Align on the boundary where stddev starts: "mean" | "(stddev)".
            parts.append("r@{}l")
        elif is_num:
            parts.append("S")
        else:
            parts.append(text_align)
    return "".join(parts)


def split_mean_std_parts(s: str) -> Tuple[str, str]:
    pair = format_mean_std(s)
    m = re.fullmatch(r"(.+)\s*\(\s*(.+)\s*\)", pair)
    if not m:
        return pair, ""
    return m.group(1).strip(), f"({m.group(2).strip()})"

def render_table(
    header: List[str],
    rows: List[List[str]],
    index: int,
    caption_prefix: str,
    label_prefix: str,
    font_size: str,
) -> str:
    pair_cols = detect_pair_columns(header, rows)
    numeric_cols = detect_numeric_columns(header, rows)
    # Pair columns are handled as split text subcolumns, not S columns.
    numeric_cols = [n and (not p) for n, p in zip(numeric_cols, pair_cols)]
    colspec = make_colspec_with_pairs(numeric_cols, pair_cols, text_align="l")

    lines = []
    lines.append(r"  \begin{center}")
    if font_size:
        lines.append(f"  {font_size}")
    lines.append(rf"  \begin{{tabular}}{{{colspec}}}")
    lines.append(r"  \toprule")

    hdr_cells = []
    for j, h in enumerate(header):
        h_esc = format_header_cell(h)
        if pair_cols[j]:
            hdr_cells.append(rf"\multicolumn{{2}}{{c}}{{{h_esc}}}")
        elif numeric_cols[j]:
            hdr_cells.append(rf"\multicolumn{{1}}{{c}}{{{h_esc}}}")
        else:
            hdr_cells.append(h_esc)
    lines.append("  " + " & ".join(hdr_cells) + r" \\")
    lines.append(r"  \midrule")

    for r in rows:
        rr = (r + [""] * len(header))[:len(header)]
        out = []
        for j, cell in enumerate(rr):
            cell = (cell or "").strip()
            if pair_cols[j]:
                if is_mean_std_like(cell):
                    mean_part, std_part = split_mean_std_parts(cell)
                    out.append(latex_escape_text(mean_part))
                    out.append(latex_escape_text(std_part))
                elif cell == "":
                    out.append("{}")
                    out.append("{}")
                else:
                    out.append("{" + latex_escape_text(cell) + "}")
                    out.append("{}")
            elif numeric_cols[j]:
                if is_number_like(cell):
                    out.append(format_number(cell))
                elif cell == "":
                    out.append("{}")
                else:
                    out.append("{" + latex_escape_text(cell) + "}")
            else:
                out.append(latex_escape_text(cell))
        lines.append("  " + " & ".join(out) + r" \\")

    lines.append(r"  \bottomrule")
    lines.append(r"  \end{tabular}")
    lines.append(rf"  \captionof{{table}}{{{latex_escape_text(caption_prefix)} {index}}}")
    lines.append(rf"  \label{{{label_prefix}{index}}}")
    lines.append(r"  \end{center}")
    return "\n".join(lines)


def convert(
    input_csv: Path,
    output_tex: Path,
    caption_prefix: str,
    label_prefix: str,
    font_size: str,
    subsection_title: str,
    subsection_label: str,
) -> int:
    tables = split_tables(input_csv)
    if not tables:
        raise RuntimeError("No tables detected in CSV.")

    inner = [
        render_table(h, r, i, caption_prefix, label_prefix, font_size)
        for i, (h, r) in enumerate(tables, start=1)
    ]

    parts = []
    parts.append(r"\clearpage")
    parts.append(r"\twocolumn[%")
    parts.append(rf"  \subsection{{{latex_escape_text(subsection_title)}}}")
    if subsection_label:
        parts.append(rf"  \label{{{subsection_label}}}")
    parts.extend(inner)
    parts.append(r"]")

    output_tex.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return len(tables)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Generic CSV -> LaTeX table* converter with siunitx numeric alignment."
    )
    p.add_argument("input_csv", type=Path, help="Input CSV file")
    p.add_argument("-o", "--output", type=Path, default=Path("tables.tex"), help="Output .tex file")
    p.add_argument("--caption-prefix", default="Results table", help="Caption prefix")
    p.add_argument("--label-prefix", default="tab:results_", help="Label prefix")
    p.add_argument(
        "--size",
        choices=["", r"\small", r"\footnotesize", r"\scriptsize"],
        default=r"\small",
        help="Font size command inside table",
    )
    p.add_argument("--subsection-title", default="Results", help="Subsection title")
    p.add_argument("--subsection-label", default="", help="Optional \\label for the subsection")
    args = p.parse_args()

    n = convert(
        input_csv=args.input_csv,
        output_tex=args.output,
        caption_prefix=args.caption_prefix,
        label_prefix=args.label_prefix,
        font_size=args.size,
        subsection_title=args.subsection_title,
        subsection_label=args.subsection_label,
    )
    print(f"Wrote {n} table(s) to {args.output}")


if __name__ == "__main__":
    main()