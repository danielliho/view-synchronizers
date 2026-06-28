#!/usr/bin/env python3
import argparse
import csv
import re
from pathlib import Path
from typing import List, Tuple


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
        num = sum(1 for x in nonempty if is_number_like(x))
        numeric[j] = (num / len(nonempty)) >= 0.8
    return numeric


def make_colspec(numeric_cols: List[bool], text_align: str = "l") -> str:
    # text columns: l/c/r ; numeric columns: S
    parts = []
    for is_num in numeric_cols:
        parts.append("S" if is_num else text_align)
    return "".join(parts)

def render_table(
    header: List[str],
    rows: List[List[str]],
    index: int,
    caption_prefix: str,
    label_prefix: str,
    font_size: str,
) -> str:
    numeric_cols = detect_numeric_columns(header, rows)
    colspec = make_colspec(numeric_cols, text_align="l")

    lines = []
    lines.append(r"  \begin{center}")
    if font_size:
        lines.append(f"  {font_size}")
    lines.append(rf"  \begin{{tabular}}{{{colspec}}}")
    lines.append(r"  \toprule")

    hdr_cells = []
    for j, h in enumerate(header):
        h_esc = latex_escape_text(h)
        if numeric_cols[j]:
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
            if numeric_cols[j]:
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