"""Render a Node 20 deprecation trend report across multiple annotations.json snapshots.

Standalone — no imports from other project modules. Takes one or more
annotations.json files on the CLI; produces a single self-contained HTML
file (inline SVG, no external resources, no JS).

Usage:
    python3 trend.py annotations.json
    python3 trend.py history/2026-04-15.json history/2026-05-01.json
    python3 trend.py history/*.json --top-n 8 --out q2_trend.html

Each input file is expected to follow the shape produced by annotations.py —
a top-level dict keyed by `<full_repo>_<N>`, each entry containing
`annotation_messages`, `workflow_name`, `repository_name`, etc.

Snapshot ordering: derived from a YYYY-MM-DD prefix in the filename when
present; falls back to file mtime (with a stderr warning) otherwise. Files
are sorted ascending by date label before rendering, regardless of CLI order.
"""
import argparse
import html
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


# Canonical and forced-runtime variants of GitHub's Node 20 deprecation
# message. Update this tuple if GitHub changes the wording — single source of
# truth for what "counts as Node 20".
NODE20_MARKERS = (
    "Node.js 20 actions are deprecated",   # canonical deprecation banner
    "Node.js 20 is deprecated",            # forced-to-Node-24 variant
)

# Same pattern used inline in deprecation.py's re.findall(...) at line 101.
# Note: actions/checkout@v3 and @v4 are intentionally counted as distinct —
# Renovate fixes are version-specific and conflating them hides which pins
# are lagging behind.
ACTION_REGEX = re.compile(r'(?:[\w-]+\/[\w-]+)@[\w\d]+(?:\.[\w\d]+)*')

# Non-action refs that occasionally appear in annotation messages (Python
# package manifests embedded in some logs). Filter so the chart doesn't list
# them as "actions".
NON_ACTION_OWNERS = frozenset({"pypi", "npm", "rubygems", "maven", "nuget"})

# Stable colour assignment for top actions; one colour per action ref across
# the whole chart so the eye can follow the same action across snapshots.
PALETTE = [
    "#fb8500", "#cf222e", "#0969da", "#1a7f37", "#8250df",
    "#bf8700", "#0a3069", "#a40e26",
]

_DATE_RE = re.compile(r'(\d{4}-\d{2}-\d{2})')


def _format_dmy(iso_str):
    """ISO `YYYY-MM-DD` (or `YYYY-MM-DDT...`) -> `DD/MM/YYYY`.
    Falls back to the first 10 chars unchanged if the string isn't ISO-shaped.
    Snapshot labels are kept ISO internally for sortable storage; this helper
    is called only at the display boundary (charts + table + meta line)."""
    if not iso_str:
        return ""
    try:
        y, m, d = iso_str[:10].split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return iso_str[:10]


# ──────────────────────────────────────────────────────────────────────
# Snapshot loading
# ──────────────────────────────────────────────────────────────────────

def extract_date_from_filename(path):
    """Pull a YYYY-MM-DD from the basename; return None if absent."""
    m = _DATE_RE.search(os.path.basename(path))
    return m.group(1) if m else None


def load_snapshots(paths):
    """Returns ordered list of (date_label, raw_data) tuples, sorted ascending.
    Skips unparseable files with a stderr warning rather than failing the run."""
    out = []
    for p in paths:
        try:
            with open(p) as f:
                data = json.load(f)
        except Exception as e:
            print(f"[warn] could not read {p}: {e}", file=sys.stderr)
            continue
        label = extract_date_from_filename(p)
        if not label:
            label = datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d")
            print(f"[warn] no date in filename {p!r}; using mtime ({label})",
                  file=sys.stderr)
        out.append((label, data))
    out.sort(key=lambda t: t[0])
    return out


# ──────────────────────────────────────────────────────────────────────
# Metric extraction
# ──────────────────────────────────────────────────────────────────────

def _matches_node20(msg):
    return msg and any(m in msg for m in NODE20_MARKERS)


def compute_snapshot_metrics(data, top_n=5):
    """Returns counts + top-N actions for one annotations.json snapshot.

    Dedupes action refs per-workflow — a workflow listing checkout@v4 twice
    in two different messages still counts as one for that ref.
    """
    node20_workflows = 0
    actions = Counter()
    for entry in data.values():
        msgs = [m for m in (entry.get("annotation_messages") or []) if m]
        node20_msgs = [m for m in msgs if _matches_node20(m)]
        if not node20_msgs:
            continue
        node20_workflows += 1
        seen = set()
        for msg in node20_msgs:
            for ref in ACTION_REGEX.findall(msg):
                if "/" not in ref:
                    continue
                owner = ref.split("/", 1)[0].lower()
                if owner in NON_ACTION_OWNERS:
                    continue
                seen.add(ref)
        for ref in seen:
            actions[ref] += 1
    return {
        "node20_workflows": node20_workflows,
        "affected_actions": actions,
        "distinct_actions": len(actions),
        "top_actions":      actions.most_common(top_n),
    }


# ──────────────────────────────────────────────────────────────────────
# SVG: headline line chart
# ──────────────────────────────────────────────────────────────────────

def render_line_chart_svg(points, title, width=720, height=240):
    """Single-series line chart. `points` = [(date_label, value), ...].
    Single-point case: draws the marker, skips the polyline."""
    pad_left, pad_right, pad_top, pad_bottom = 56, 24, 36, 56
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    values = [v for _, v in points]
    y_max = max(values) if values else 1
    y_max = y_max or 1
    n = len(points)

    def x_for(i):
        if n == 1:
            return pad_left + plot_w / 2
        return pad_left + (i / (n - 1)) * plot_w

    def y_for(v):
        return pad_top + plot_h - (v / y_max) * plot_h

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg">',
        f'<text x="{pad_left}" y="20" font-size="14" font-weight="600" '
        f'fill="#1f2328">{html.escape(title)}</text>',
        f'<line x1="{pad_left}" y1="{pad_top}" x2="{pad_left}" y2="{pad_top+plot_h}" stroke="#d0d7de"/>',
        f'<line x1="{pad_left}" y1="{pad_top+plot_h}" x2="{pad_left+plot_w}" y2="{pad_top+plot_h}" stroke="#d0d7de"/>',
    ]
    # Gridlines + Y labels at 0, mid, max
    for frac, label_val in ((0, 0), (0.5, y_max // 2), (1.0, y_max)):
        y = pad_top + plot_h - frac * plot_h
        parts.append(
            f'<line x1="{pad_left}" y1="{y:.1f}" x2="{pad_left+plot_w}" y2="{y:.1f}" '
            f'stroke="#eaeef2" stroke-dasharray="2,3"/>'
        )
        parts.append(
            f'<text x="{pad_left-8}" y="{y+4:.1f}" font-size="11" fill="#57606a" '
            f'text-anchor="end">{int(label_val)}</text>'
        )

    # Trend polyline (skip if only one point)
    if n >= 2:
        pts = " ".join(f"{x_for(i):.1f},{y_for(v):.1f}" for i, (_, v) in enumerate(points))
        parts.append(f'<polyline points="{pts}" fill="none" stroke="#0969da" stroke-width="2"/>')

    # Markers + per-point value labels
    for i, (label, v) in enumerate(points):
        cx, cy = x_for(i), y_for(v)
        display = _format_dmy(label)
        parts.append(
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="4" fill="#0969da">'
            f'<title>{html.escape(display)}: {v}</title>'
            f'</circle>'
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{cy-10:.1f}" font-size="11" fill="#1f2328" '
            f'text-anchor="middle">{v}</text>'
        )

    # X-axis tick labels; rotate when more than four to avoid overlap
    rotate = n > 4
    for i, (label, _) in enumerate(points):
        cx = x_for(i)
        y_lbl = pad_top + plot_h + 18
        display = _format_dmy(label)
        if rotate:
            parts.append(
                f'<text x="{cx:.1f}" y="{y_lbl:.1f}" font-size="11" fill="#57606a" '
                f'text-anchor="end" transform="rotate(-30 {cx:.1f} {y_lbl:.1f})">'
                f'{html.escape(display)}</text>'
            )
        else:
            parts.append(
                f'<text x="{cx:.1f}" y="{y_lbl:.1f}" font-size="11" fill="#57606a" '
                f'text-anchor="middle">{html.escape(display)}</text>'
            )

    parts.append('</svg>')
    return "".join(parts)


# ──────────────────────────────────────────────────────────────────────
# SVG: top-actions grouped bar chart
# ──────────────────────────────────────────────────────────────────────

def render_top_actions_chart_svg(snapshots, top_n=5, width=720, height=320):
    """Grouped bars: one cluster per snapshot date, one bar per top-N action.
    Top-N is computed across the union of snapshots so an action that's hot in
    one snapshot but absent in another shows a 0-height bar where appropriate."""
    union = Counter()
    for _, m in snapshots:
        for ref, n in m["top_actions"]:
            union[ref] = max(union[ref], n)
    top_refs = [ref for ref, _ in union.most_common(top_n)]
    if not top_refs:
        return ('<svg viewBox="0 0 720 80" width="100%" height="80" '
                'xmlns="http://www.w3.org/2000/svg">'
                '<text x="56" y="30" font-size="14" font-weight="600" fill="#1f2328">'
                'Top affected actions per snapshot</text>'
                '<text x="56" y="56" font-size="12" fill="#57606a" font-style="italic">'
                'No Node 20-affecting actions detected in any snapshot.</text>'
                '</svg>')

    color = {ref: PALETTE[i % len(PALETTE)] for i, ref in enumerate(top_refs)}

    pad_left, pad_right, pad_top, pad_bottom = 56, 24, 40, 110
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    n_groups = len(snapshots)
    n_bars = len(top_refs)
    group_w = plot_w / n_groups if n_groups else plot_w
    bar_w = (group_w * 0.8) / max(n_bars, 1)
    group_gap = group_w * 0.1
    y_max = max((m["affected_actions"].get(ref, 0)
                 for _, m in snapshots for ref in top_refs), default=1) or 1

    parts = [
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'xmlns="http://www.w3.org/2000/svg">',
        f'<text x="{pad_left}" y="20" font-size="14" font-weight="600" '
        f'fill="#1f2328">Top affected actions per snapshot</text>',
        f'<line x1="{pad_left}" y1="{pad_top}" x2="{pad_left}" y2="{pad_top+plot_h}" stroke="#d0d7de"/>',
        f'<line x1="{pad_left}" y1="{pad_top+plot_h}" x2="{pad_left+plot_w}" y2="{pad_top+plot_h}" stroke="#d0d7de"/>',
    ]
    for frac, label_val in ((0, 0), (0.5, y_max // 2), (1.0, y_max)):
        y = pad_top + plot_h - frac * plot_h
        parts.append(
            f'<text x="{pad_left-8}" y="{y+4:.1f}" font-size="11" fill="#57606a" '
            f'text-anchor="end">{int(label_val)}</text>'
        )

    for gi, (label, metrics) in enumerate(snapshots):
        group_x = pad_left + gi * group_w + group_gap
        display = _format_dmy(label)
        for bi, ref in enumerate(top_refs):
            v = metrics["affected_actions"].get(ref, 0)
            bx = group_x + bi * bar_w
            bh = (v / y_max) * plot_h if y_max else 0
            by = pad_top + plot_h - bh
            parts.append(
                f'<rect x="{bx:.1f}" y="{by:.1f}" width="{max(bar_w-1, 1):.1f}" '
                f'height="{bh:.1f}" fill="{color[ref]}">'
                f'<title>{html.escape(ref)} @ {html.escape(display)}: {v}</title>'
                f'</rect>'
            )
            # Numeric label above each non-zero bar (skipped at zero to avoid
            # clutter; tooltip on the rect still shows "ref @ date: 0" if needed).
            if v > 0:
                label_cx = bx + max(bar_w - 1, 1) / 2
                label_cy = by - 3
                parts.append(
                    f'<text x="{label_cx:.1f}" y="{label_cy:.1f}" font-size="9" '
                    f'fill="#1f2328" text-anchor="middle">{v}</text>'
                )
        cx = group_x + (bar_w * n_bars) / 2
        parts.append(
            f'<text x="{cx:.1f}" y="{pad_top+plot_h+16:.1f}" font-size="11" '
            f'fill="#57606a" text-anchor="middle">{html.escape(display)}</text>'
        )

    # Legend below the chart; wrap to a second column after 4 entries
    legend_top = pad_top + plot_h + 36
    legend_line_h = 16
    legend_col_w = plot_w / 2
    for i, ref in enumerate(top_refs):
        col = i // 4
        row = i % 4
        lx = pad_left + col * legend_col_w
        ly = legend_top + row * legend_line_h
        parts.append(
            f'<rect x="{lx:.1f}" y="{ly:.1f}" width="10" height="10" fill="{color[ref]}"/>'
        )
        parts.append(
            f'<text x="{lx+14:.1f}" y="{ly+9:.1f}" font-size="11" fill="#1f2328">'
            f'{html.escape(ref)}</text>'
        )

    parts.append('</svg>')
    return "".join(parts)


# ──────────────────────────────────────────────────────────────────────
# HTML assembly
# ──────────────────────────────────────────────────────────────────────

CSS = """
* { box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    margin: 0 auto; padding: 32px; max-width: 960px;
    color: #1f2328; line-height: 1.5;
}
h1 { margin: 0 0 8px 0; font-size: 22px; font-weight: 600; }
.meta { color: #57606a; font-size: 13px; margin-bottom: 24px; }
.chart {
    background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px;
    padding: 16px; margin: 16px 0;
}
table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 24px; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid #eaeef2; }
th {
    background: #f6f8fa; font-weight: 600; color: #57606a; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.4px;
}
.ref {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    background: #f6f8fa; padding: 1px 6px; border-radius: 3px; font-size: 12px;
}
.empty { color: #57606a; font-style: italic; }
"""


def render_html(snapshots, top_n=5):
    """`snapshots` = [(date_label, metrics_dict), ...] in ascending date order."""
    if not snapshots:
        return "<!doctype html><html><body><p>No snapshots loaded.</p></body></html>"

    generated_at = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    line_points = [(label, m["node20_workflows"]) for label, m in snapshots]

    rows = []
    for label, m in snapshots:
        if m["top_actions"]:
            top_ref, top_cnt = m["top_actions"][0]
            top_cell = f'<span class="ref">{html.escape(top_ref)}</span> ({top_cnt})'
        else:
            top_cell = '<span class="empty">none</span>'
        rows.append(
            f'<tr><td>{html.escape(_format_dmy(label))}</td>'
            f'<td>{m["node20_workflows"]}</td>'
            f'<td>{m["distinct_actions"]}</td>'
            f'<td>{top_cell}</td></tr>'
        )

    snap_count = len(snapshots)
    return (
        "<!doctype html>"
        '<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Node 20 Deprecation Trend</title>'
        f'<style>{CSS}</style></head><body>'
        '<h1>Node 20 Deprecation Trend</h1>'
        f'<div class="meta">Generated {html.escape(generated_at)} · '
        f'{snap_count} snapshot{"s" if snap_count != 1 else ""}</div>'
        '<div class="chart">'
        f'{render_line_chart_svg(line_points, "Node 20-affected workflows over time")}'
        '</div>'
        '<div class="chart">'
        f'{render_top_actions_chart_svg(snapshots, top_n=top_n)}'
        '</div>'
        '<table><thead><tr><th>Date</th><th>Node 20 Workflows</th>'
        '<th>Distinct Affected Actions</th><th>Top Affected Action</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
        '</body></html>'
    )


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Render a Node 20 deprecation trend report from one or "
                    "more annotations.json snapshots."
    )
    ap.add_argument("paths", nargs="+",
                    help="One or more annotations.json files. Recommended "
                         "filename convention: YYYY-MM-DD prefix (e.g. "
                         "2026-04-15.json) so the trend axis is meaningful. "
                         "Files without a date in the filename fall back to "
                         "mtime with a stderr warning.")
    ap.add_argument("--out", default="trend_report.html",
                    help="Output HTML path (default: trend_report.html)")
    ap.add_argument("--top-n", type=int, default=5,
                    help="Top N affected actions to chart (default: 5)")
    args = ap.parse_args()

    raw = load_snapshots(args.paths)
    if not raw:
        print("[error] no snapshots loaded — exiting.", file=sys.stderr)
        sys.exit(1)

    snapshots = [(label, compute_snapshot_metrics(data, top_n=args.top_n))
                 for label, data in raw]

    Path(args.out).write_text(render_html(snapshots, top_n=args.top_n), encoding="utf-8")
    print(f"wrote {args.out} "
          f"({len(snapshots)} snapshot{'s' if len(snapshots) != 1 else ''})")

    # Machine-readable digest line — the GHA-Trend-Reporter Jenkins pipeline
    # scrapes this from stdout to build its Slack post. Mirrors the
    # [GHA_DEP_SUMMARY] pattern emitted by render_report.py.
    first_label, first_metrics = snapshots[0]
    last_label, last_metrics   = snapshots[-1]
    summary = {
        "snapshots": len(snapshots),
        "first":     first_label,
        "last":      last_label,
        "first_n20": first_metrics["node20_workflows"],
        "last_n20":  last_metrics["node20_workflows"],
        "delta":     last_metrics["node20_workflows"] - first_metrics["node20_workflows"],
    }
    print(f"[TREND_SUMMARY] {json.dumps(summary)}")


if __name__ == "__main__":
    main()
