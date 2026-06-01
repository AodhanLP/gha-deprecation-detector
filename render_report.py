"""Render annotations.json to a single self-contained HTML report.

Usage: python3.11 render_report.py [input.json] [output.html]
Defaults: annotations.json -> annotations_report.html
"""
import html
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from deprecation import ACTION_REGEX, NON_ACTION_OWNERS

INPUT_DEFAULT = Path("annotations.json")
OUTPUT_DEFAULT = Path("annotations_report.html")


CSS = """
* { box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    margin: 0; background: #f7f8fa; color: #1f2328; line-height: 1.5;
}
header { background: #1f2328; color: #fff; padding: 24px 32px; }
header h1 { margin: 0 0 8px 0; font-size: 22px; font-weight: 600; }
header .meta { font-size: 13px; opacity: 0.75; }
.summary {
    display: flex; gap: 12px; padding: 16px 32px;
    background: #fff; border-bottom: 1px solid #d0d7de; flex-wrap: wrap;
}
.tile {
    flex: 1 1 140px; background: #f6f8fa; padding: 12px 16px;
    border-radius: 6px; border: 1px solid #d0d7de;
}
.tile .num { font-size: 24px; font-weight: 600; }
.tile .lab { font-size: 12px; color: #57606a; text-transform: uppercase; letter-spacing: 0.4px; }
.toc { padding: 16px 32px; background: #fff; border-bottom: 1px solid #d0d7de; }
.toc h2 { margin: 0 0 8px 0; font-size: 14px; text-transform: uppercase; color: #57606a; letter-spacing: 0.4px; }
.toc ul { margin: 0; padding: 0; list-style: none; columns: 3; column-gap: 24px; }
.toc li { break-inside: avoid; padding: 2px 0; }
.toc a { color: #0969da; text-decoration: none; font-size: 13px; }
.toc .count { color: #57606a; font-size: 12px; }
main { padding: 24px 32px; }
.repo {
    background: #fff; border: 1px solid #d0d7de; border-radius: 6px;
    margin-bottom: 16px; overflow: hidden;
}
.repo h2 {
    margin: 0; padding: 12px 16px; border-bottom: 1px solid #d0d7de;
    background: #f6f8fa; font-size: 16px; font-weight: 600;
}
.repo h2 .badge {
    display: inline-block; background: #ddf4ff; color: #0969da;
    padding: 1px 8px; border-radius: 10px; font-size: 12px;
    margin-left: 8px; vertical-align: middle;
}
.workflow { padding: 12px 16px; border-bottom: 1px solid #eaeef2; }
.workflow:last-child { border-bottom: none; }
.workflow h3 { margin: 0 0 4px 0; font-size: 14px; font-weight: 600; }
.workflow .path {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px; color: #57606a; margin-bottom: 8px;
}
.messages { margin: 0; padding: 0; list-style: none; }
.messages li {
    background: #fff8c5; border: 1px solid #d4a72c; border-left-width: 4px;
    padding: 8px 12px; margin-bottom: 6px; border-radius: 4px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px; white-space: pre-wrap; word-break: break-word;
}
.messages li.deprecation { background: #fff1e5; border-color: #fb8500; }
.messages li.error { background: #ffebe9; border-color: #cf222e; }
.empty { padding: 32px; text-align: center; color: #57606a; }
.charts {
    display: flex; gap: 16px; padding: 16px 32px; flex-wrap: wrap;
    background: #fff; border-bottom: 1px solid #d0d7de;
}
.chart-card {
    flex: 1 1 380px; background: #f6f8fa; border: 1px solid #d0d7de;
    border-radius: 6px; padding: 16px;
}
.chart-card h3 {
    margin: 0 0 12px 0; font-size: 13px; text-transform: uppercase;
    color: #57606a; letter-spacing: 0.4px;
}
.donut-wrap { display: flex; gap: 16px; align-items: center; }
.legend { list-style: none; margin: 0; padding: 0; font-size: 12px; flex: 1; }
.legend li { padding: 3px 0; display: flex; align-items: center; gap: 8px; }
.legend .swatch {
    display: inline-block; width: 12px; height: 12px; border-radius: 2px;
    flex-shrink: 0;
}
.legend .count { color: #57606a; margin-left: auto; font-variant-numeric: tabular-nums; }
.legend a {
    display: flex; align-items: center; gap: 8px; flex: 1;
    color: inherit; text-decoration: none;
    padding: 3px 4px; border-radius: 3px;
}
.legend a:hover { background: #eaeef2; }
.legend a span { display: inline-block; }
.legend .legend-label { flex: 1; }
.bars text { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
html { scroll-behavior: smooth; }
svg a { cursor: pointer; }
svg a circle:hover { opacity: 0.85; }
.category-detail {
    display: none;
    background: #fff; border: 1px solid #d0d7de; border-radius: 6px;
    margin: 0 32px 16px; overflow: hidden;
}
.category-detail:target { display: block; }
.cat-head {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 16px; background: #f6f8fa; border-bottom: 1px solid #d0d7de;
}
.cat-head h3 { margin: 0; font-size: 14px; font-weight: 600; }
.cat-head .dot {
    display: inline-block; width: 10px; height: 10px;
    border-radius: 50%; margin-right: 8px; vertical-align: middle;
}
.cat-head .muted { color: #57606a; font-weight: 400; margin-left: 6px; }
.cat-head .back { color: #0969da; text-decoration: none; font-size: 13px; }
.cat-head .back:hover { text-decoration: underline; }
.category-detail table { width: 100%; border-collapse: collapse; font-size: 13px; }
.category-detail th, .category-detail td {
    text-align: left; padding: 8px 16px; border-bottom: 1px solid #eaeef2;
}
.category-detail th {
    font-weight: 600; color: #57606a;
    font-size: 11px; text-transform: uppercase; letter-spacing: 0.4px;
}
.category-detail td.path {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px; color: #57606a;
}
.category-detail tbody tr { cursor: help; }
.category-detail tbody tr:hover { background: #f6f8fa; }
.affected-actions {
    padding: 12px 16px; border-bottom: 1px solid #eaeef2;
    background: #fafbfc;
}
.affected-actions h4 {
    margin: 0 0 8px 0; font-size: 11px; font-weight: 600;
    text-transform: uppercase; color: #57606a; letter-spacing: 0.4px;
}
.affected-actions ul { margin: 0; padding: 0; list-style: none; }
.affected-actions li {
    padding: 6px 0; font-size: 13px;
    border-bottom: 1px dotted #eaeef2;
    display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px;
}
.affected-actions li:last-child { border-bottom: none; }
.affected-actions .ref {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    background: #f6f8fa; padding: 1px 6px; border-radius: 3px;
    font-size: 12px; color: #1f2328;
    text-decoration: none;
}
.affected-actions a.ref:hover {
    background: #ddf4ff; color: #0969da;
}
.action-remediation {
    padding: 10px 16px; background: #f6f8fa;
    border-bottom: 1px solid #d0d7de;
    font-size: 13px;
}
.action-remediation code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    background: #fff; padding: 1px 6px; border-radius: 3px;
    font-size: 12px;
}
.affected-actions .count {
    color: #57606a; font-size: 12px;
    cursor: help; border-bottom: 1px dotted #57606a;
}
.affected-actions .remediation { color: #1f2328; flex: 1; min-width: 240px; }
.affected-actions .remediation.up { color: #1a7f37; }
.affected-actions .remediation.stuck { color: #cf222e; }
.affected-actions .remediation.muted { color: #57606a; }
.notes-link {
    color: #0969da; text-decoration: none; font-size: 12px;
    margin-left: 4px;
}
.notes-link:hover { text-decoration: underline; }
.breaking-warn {
    color: #9a6700; background: #fff8c5;
    padding: 1px 6px; border-radius: 3px;
    font-size: 12px; margin-left: 6px; cursor: help;
    border: 1px solid #d4a72c;
}
.suites {
    display: flex; gap: 12px; padding: 16px 32px; flex-wrap: wrap;
    background: #fff; border-bottom: 1px solid #d0d7de;
}
.suites-heading {
    width: 100%; margin: 0 0 4px 0; font-size: 13px;
    text-transform: uppercase; color: #57606a; letter-spacing: 0.4px;
}
.suite-card {
    flex: 1 1 240px; background: #f6f8fa; border: 1px solid #d0d7de;
    border-radius: 6px; padding: 12px;
}
.suite-card h4 { margin: 0 0 8px 0; font-size: 14px; font-weight: 600; }
.suite-card h4 .muted {
    color: #57606a; font-weight: 400; font-size: 12px; margin-left: 6px;
}
.suite-card .donut-wrap { display: flex; gap: 12px; align-items: center; }
.suite-card .empty {
    color: #57606a; font-size: 12px; padding: 24px 0; text-align: center;
}
.category-detail tbody td { padding: 0; }
.category-detail tbody td .row-link {
    display: block; padding: 8px 16px;
    color: inherit; text-decoration: none;
}
.category-detail tbody td.path .row-link {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: 12px; color: #57606a;
}
.workflow:target { background: #fff8c5; }
.run-link {
    color: inherit; text-decoration: none;
    border-bottom: 1px dashed rgba(31, 35, 40, 0.25);
}
.run-link:hover { color: #0969da; border-bottom-color: #0969da; }
.run-link .run-arrow { color: #57606a; font-size: 0.85em; margin-left: 2px; }
.run-link:hover .run-arrow { color: #0969da; }
.category-detail tbody td.wf-cell { padding: 0; }
.category-detail tbody td.wf-cell .run-link {
    display: block; padding: 8px 16px;
    border-bottom: none;
}
.category-detail tbody td.wf-cell .run-link:hover { background: #ddf4ff; }
.to-top {
    position: fixed; bottom: 24px; right: 24px;
    width: 40px; height: 40px; border-radius: 50%;
    background: #1f2328; color: #fff;
    display: flex; align-items: center; justify-content: center;
    text-decoration: none; font-size: 20px; font-weight: 600;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    opacity: 0.85; transition: opacity 0.15s;
    z-index: 100;
}
.to-top:hover { opacity: 1; }
"""

PALETTE = [
    "#fb8500", "#cf222e", "#0969da", "#1a7f37", "#8250df",
    "#bf8700", "#0a3069", "#a40e26", "#0550ae", "#57606a",
]

def load_buckets():
    """Load (label, pattern) pairs from buckets.json. Order is significant —
    first matching pattern wins, so put specific patterns before generic ones.
    Returns [] if the file is absent; bucket() will fall through to the
    generic 'Other deprecation' / 'Errors' / 'Other warnings' classifiers."""
    path = Path("buckets.json")
    if not path.exists():
        return []
    raw = json.loads(path.read_text())
    return [(item["label"], item["pattern"]) for item in raw]


DEPRECATION_BUCKETS = load_buckets()


def bucket(msg):
    low = msg.lower()
    for label, pattern in DEPRECATION_BUCKETS:
        if pattern in low:
            return label
    if "deprecat" in low:
        return "Other deprecation"
    if "error" in low or "fail" in low:
        return "Errors"
    return "Other warnings"


def normalize_message(msg):
    """For the top-messages chart: collapse known-deprecation variants that
    only differ in the trailing action list. Non-matching messages pass through
    unchanged so distinct errors/warnings still surface individually."""
    low = msg.lower()
    for _, pattern in DEPRECATION_BUCKETS:
        if pattern in low and ":" in msg:
            return msg.split(":", 1)[0] + ": ..."
    return msg


def bucket_id(label, prefix=""):
    s = "".join(c.lower() if c.isalnum() else "-" for c in label)
    base = "cat-" + s.strip("-")
    return f"{prefix}-{base}" if prefix else base


def slug(name):
    return "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")


def entry_id(key):
    return "wf-" + "".join(c if c.isalnum() else "-" for c in key)


def donut_svg(slices, size=180, stroke=28, id_prefix=""):
    """slices: list of (label, count, color). Returns SVG string.
    `id_prefix` scopes the slice fragment links (e.g. 'hub' -> #hub-cat-...)."""
    import math
    total = sum(c for _, c, _ in slices)
    if total == 0:
        return ""
    r = (size - stroke) / 2
    cx = cy = size / 2
    circ = 2 * math.pi * r
    parts = [f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}">']
    offset = 0.0
    for label, count, color in slices:
        dash = (count / total) * circ
        parts.append(
            f'<a href="#{bucket_id(label, id_prefix)}">'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
            f'stroke="{color}" stroke-width="{stroke}" '
            f'stroke-dasharray="{dash:.3f} {circ:.3f}" '
            f'stroke-dashoffset="{-offset:.3f}" '
            f'transform="rotate(-90 {cx} {cy})">'
            f'<title>{html.escape(label)}: {count}</title>'
            f'</circle>'
            f'</a>'
        )
        offset += dash
    parts.append(
        f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" '
        f'font-size="20" font-weight="600" fill="#1f2328">{total}</text>'
        f'<text x="{cx}" y="{cy + 14}" text-anchor="middle" '
        f'font-size="10" fill="#57606a">workflows</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def legend_html(slices, id_prefix=""):
    out = ['<ul class="legend">']
    for label, count, color in slices:
        out.append(
            f'<li><a href="#{bucket_id(label, id_prefix)}">'
            f'<span class="swatch" style="background:{color}"></span>'
            f'<span class="legend-label">{html.escape(label)}</span>'
            f'<span class="count">{count}</span>'
            f'</a></li>'
        )
    out.append("</ul>")
    return "".join(out)


def bar_chart_svg(rows, width=560, row_height=22):
    """rows: list of (label, count). Sorted by caller."""
    if not rows:
        return ""
    max_count = max(c for _, c in rows)
    label_w = 280
    bar_max = width - label_w - 50
    max_chars = 40  # fits within label_w at font-size 11 monospace
    height = row_height * len(rows) + 8
    parts = [f'<svg class="bars" viewBox="0 0 {width} {height}" width="100%" height="{height}">']
    for i, (label, count) in enumerate(rows):
        y = i * row_height + 14
        bar_w = (count / max_count) * bar_max if max_count else 0
        truncated = label if len(label) <= max_chars else label[:max_chars - 1] + "…"
        full = html.escape(label)
        parts.append(
            f'<text x="0" y="{y}" font-size="11" fill="#1f2328">'
            f'{html.escape(truncated)}<title>{full}</title></text>'
            f'<rect x="{label_w}" y="{y - 11}" width="{bar_w:.1f}" height="14" '
            f'fill="#0969da" rx="2" />'
            f'<text x="{label_w + bar_w + 6:.1f}" y="{y}" font-size="11" '
            f'fill="#57606a">{count}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def compute_bucket_counts(data):
    """Returns ordered list of (label, count) — workflow count per bucket."""
    bucket_counts = defaultdict(int)
    for entry in data.values():
        msgs = [m for m in (entry.get("annotation_messages") or []) if m]
        seen_buckets = set()
        for msg in set(msgs):
            b = bucket(msg)
            if b not in seen_buckets:
                bucket_counts[b] += 1
                seen_buckets.add(b)
    return sorted(bucket_counts.items(), key=lambda kv: -kv[1])


def compute_analytics(data):
    """Returns (bucket_slices, top_messages) for chart rendering."""
    sorted_buckets = compute_bucket_counts(data)
    bucket_slices = [
        (label, count, PALETTE[i % len(PALETTE)])
        for i, (label, count) in enumerate(sorted_buckets)
    ]

    message_counts = defaultdict(int)
    for entry in data.values():
        msgs = [m for m in (entry.get("annotation_messages") or []) if m]
        seen_normalized = set()
        for msg in set(msgs):
            n = normalize_message(msg)
            if n not in seen_normalized:
                message_counts[n] += 1
                seen_normalized.add(n)
    top_messages = sorted(message_counts.items(), key=lambda kv: -kv[1])[:10]
    return bucket_slices, top_messages


def _norm_name(s):
    return "".join(c.lower() for c in s if c.isalnum())


def load_suites():
    """Returns {suite_name: set(normalised_product_names)} or {} if no file."""
    path = Path("suites.json")
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return {suite: {_norm_name(p) for p in products} for suite, products in raw.items()}


def repo_base_from_key(key):
    """Extract `repo-name` from a data key like `HT2-Labs/repo-name_1`."""
    repo_full = key.rsplit("_", 1)[0] if "_" in key else key
    return repo_full.split("/", 1)[-1]


def compute_suite_breakdowns(data, suites):
    """Returns list of dicts: [{name, repos, runs, slices}] in display order.
    Defined suites come first (sorted by run count desc), then 'Other' last."""
    if not suites:
        return []
    member_norm = set()
    for members in suites.values():
        member_norm.update(members)

    # Bucket data entries by suite.
    by_suite = defaultdict(dict)        # suite_name -> {key: entry}
    suite_repos = defaultdict(set)       # suite_name -> {repo_base}
    for key, entry in data.items():
        base = repo_base_from_key(key)
        norm = _norm_name(base)
        assigned = "Other"
        for suite, members in suites.items():
            if norm in members:
                assigned = suite
                break
        by_suite[assigned][key] = entry
        suite_repos[assigned].add(base)

    # Build a colour map keyed by bucket label using overall ordering, so the
    # same category gets the same colour across every donut on the page.
    overall = compute_bucket_counts(data)
    color_map = {label: PALETTE[i % len(PALETTE)] for i, (label, _) in enumerate(overall)}

    rows = []
    for suite_name, sub in by_suite.items():
        counts = compute_bucket_counts(sub)
        slices = [(label, count, color_map.get(label, "#57606a")) for label, count in counts]
        rows.append({
            "name":  suite_name,
            "slug":  slug(suite_name),
            "repos": len(suite_repos[suite_name]),
            "runs":  len(sub),
            "slices": slices,
            "data":  sub,
        })
    # Show defined suites sorted by run count desc, with Other last.
    other = [r for r in rows if r["name"] == "Other"]
    defined = [r for r in rows if r["name"] != "Other"]
    defined.sort(key=lambda r: -r["runs"])
    return defined + other


def suites_html(breakdowns):
    if not breakdowns:
        return ""
    parts = ['<section class="suites">']
    parts.append('<h2 class="suites-heading">By suite</h2>')
    for row in breakdowns:
        parts.append('<div class="suite-card">')
        parts.append(
            f'<h4>{html.escape(row["name"])}'
            f'<span class="muted">{row["repos"]} repo{"s" if row["repos"] != 1 else ""}'
            f' · {row["runs"]} run{"s" if row["runs"] != 1 else ""}</span></h4>'
        )
        if row["slices"]:
            parts.append('<div class="donut-wrap">')
            parts.append(donut_svg(row["slices"], size=140, stroke=22, id_prefix=row["slug"]))
            parts.append(legend_html(row["slices"], id_prefix=row["slug"]))
            parts.append('</div>')
        else:
            parts.append('<div class="empty">No annotations captured</div>')
        parts.append('</div>')
    parts.append('</section>')
    return "".join(parts)


def compute_action_workflows(data):
    """Return {action_ref: [{repo, workflow_name, workflow_path, key, run_url}, ...]}
    — every workflow that mentions each action, deduped per workflow."""
    out = defaultdict(dict)  # action_ref -> {entry_key: row_info}
    for key, entry in data.items():
        repo_full = key.rsplit("_", 1)[0] if "_" in key else key
        info = {
            "repo": repo_full,
            "workflow_name": entry.get("workflow_name") or "unknown",
            "workflow_path": entry.get("workflow_path") or "",
            "run_url": entry.get("run_url") or "",
            "key": key,
        }
        msgs = [m for m in (entry.get("annotation_messages") or []) if m]
        seen_refs = set()
        for msg in set(msgs):
            for ref in ACTION_REGEX.findall(msg):
                if "@" not in ref or "/" not in ref:
                    continue
                owner = ref.split("/", 1)[0].lower()
                if owner in NON_ACTION_OWNERS:
                    continue
                seen_refs.add(ref)
        for ref in seen_refs:
            if key not in out[ref]:
                out[ref][key] = info
    return {
        ref: sorted(infos.values(),
                    key=lambda r: (r["repo"].lower(), r["workflow_name"].lower()))
        for ref, infos in out.items()
    }


def action_id(ref):
    return "action-" + slug(ref)


def compute_affected_actions(data):
    """Return {bucket_label: {action_ref: [{repo, workflow_name}, ...]}}.
    A workflow that lists the same action twice in one message counts once."""
    by_bucket = defaultdict(lambda: defaultdict(list))
    for key, entry in data.items():
        repo_full = key.rsplit("_", 1)[0] if "_" in key else key
        wf_name = entry.get("workflow_name") or "unknown"
        msgs = [m for m in (entry.get("annotation_messages") or []) if m]
        seen = set()  # (bucket, ref) pairs already counted for this workflow
        for msg in set(msgs):
            b = bucket(msg)
            for ref in ACTION_REGEX.findall(msg):
                if "@" not in ref or "/" not in ref:
                    continue
                owner = ref.split("/", 1)[0].lower()
                if owner in NON_ACTION_OWNERS:
                    continue
                seen.add((b, ref))
        for b, ref in seen:
            by_bucket[b][ref].append({"repo": repo_full, "workflow_name": wf_name})
    return {b: dict(refs) for b, refs in by_bucket.items()}


def load_action_status():
    """Read action_status.json (written by probe_actions.py). Returns the
    `actions` map or {} if absent/unparseable so render still works."""
    path = Path("action_status.json")
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text()).get("actions", {})
    except Exception as e:
        print(f"[render] couldn't parse action_status.json: {e}", file=sys.stderr)
        return {}


def _repo_key(action_ref):
    """`actions/cache/restore@v4` -> `actions/cache`."""
    path = action_ref.split("@", 1)[0]
    parts = path.split("/")
    return "/".join(parts[:2]) if len(parts) >= 2 else path


def _format_dmy(iso_str):
    """`2026-01-09T00:00:00Z` -> `09/01/2026`. Falls back to the raw string."""
    if not iso_str:
        return ""
    try:
        y, m, d = iso_str[:10].split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return iso_str[:10]


def remediation_for(action_ref, status_map):
    """Returns (html_string, css_class). Falls back gracefully when status_map
    has no entry for this action (e.g. probe wasn't run)."""
    status = status_map.get(_repo_key(action_ref)) if status_map else None
    if not status:
        return ("Upstream check not run.", "muted")
    verdict = status.get("verdict")
    if verdict == "newer_node24_available":
        pin = status.get("suggested_pin", "?")
        date = _format_dmy(status.get("latest_release_date"))
        url = status.get("latest_release_url", "")
        repo = _repo_key(action_ref)
        notes_link = (
            f' <a class="notes-link" href="{html.escape(url)}" '
            f'target="_blank" rel="noopener" '
            f'title="View release notes on GitHub">'
            f'release notes <span class="run-arrow">&#8599;</span></a>'
        ) if url else ""
        breaking = (
            ' <span class="breaking-warn" '
            'title="Release notes mention breaking changes — review before bumping.">'
            '&#9888; mentions breaking changes</span>'
        ) if status.get("notes_mention_breaking") else ""
        return (
            f'Update to <code>{html.escape(repo)}@{html.escape(pin)}</code>'
            f' (Node 24{f", released {html.escape(date)}" if date else ""}).'
            f'{notes_link}{breaking}',
            "up",
        )
    if verdict == "pin_already_node24":
        date = _format_dmy(status.get("latest_release_date"))
        url = status.get("latest_release_url", "")
        notes_link = (
            f' <a class="notes-link" href="{html.escape(url)}" '
            f'target="_blank" rel="noopener">release notes '
            f'<span class="run-arrow">&#8599;</span></a>'
        ) if url else ""
        suffix = f" (latest {date}).{notes_link}" if date else f".{notes_link}"
        return (f"Already on latest Node 24 release — annotation may be stale{suffix}", "up")
    if verdict == "latest_still_node20":
        return ("No Node 24 upstream upgrade available.", "stuck")
    if verdict == "non_node_runtime":
        return ("Composite/Docker runtime — not affected by Node 24 deprecation.", "muted")
    if verdict == "internal":
        return ("Internal action — needs maintainer update.", "muted")
    if verdict == "probe_failed":
        return ("Could not check upstream (private or removed).", "muted")
    return ("Upstream check not run.", "muted")


def summary_for(data):
    """One-line digest the pipeline can scrape from stdout."""
    bucket_counts = defaultdict(int)
    repos = set()
    for key, entry in data.items():
        repos.add(key.rsplit("_", 1)[0] if "_" in key else key)
        msgs = [m for m in (entry.get("annotation_messages") or []) if m]
        for b in {bucket(m) for m in set(msgs)}:
            bucket_counts[b] += 1
    sorted_buckets = sorted(bucket_counts.items(), key=lambda kv: -kv[1])[:8]
    return {
        "repos": len(repos),
        "workflows": len(data),
        "buckets": [{"label": l, "count": c} for l, c in sorted_buckets],
    }


def compute_category_detail(data):
    """Returns {bucket_label: [{key, repo, workflow_name, workflow_path, messages}]}."""
    by_bucket = defaultdict(list)
    for key, entry in data.items():
        msgs = [m for m in (entry.get("annotation_messages") or []) if m]
        if not msgs:
            continue
        repo_full = key.rsplit("_", 1)[0] if "_" in key else key
        per_bucket_msgs = defaultdict(list)
        for m in set(msgs):
            per_bucket_msgs[bucket(m)].append(m)
        for b, bms in per_bucket_msgs.items():
            by_bucket[b].append({
                "key": key,
                "repo": repo_full,
                "workflow_name": entry.get("workflow_name", ""),
                "workflow_path": entry.get("workflow_path", ""),
                "run_url": entry.get("run_url") or "",
                "messages": sorted(bms),
            })
    for b in by_bucket:
        by_bucket[b].sort(key=lambda r: (r["repo"].lower(), str(r["workflow_name"]).lower()))
    return by_bucket


def render_category_details(by_bucket, slices_with_color, id_prefix="", title_suffix="",
                             affected_actions=None, action_status=None):
    parts = []
    affected_actions = affected_actions or {}
    action_status    = action_status or {}
    for label, _count, color in slices_with_color:
        rows = by_bucket.get(label, [])
        if not rows:
            continue
        bid = bucket_id(label, id_prefix)
        parts.append(f'<section class="category-detail" id="{bid}">')
        parts.append(
            '<div class="cat-head">'
            f'<h3><span class="dot" style="background:{color}"></span>'
            f'{html.escape(label)}{html.escape(title_suffix)}'
            f'<span class="muted">({len(rows)} workflow run(s))</span></h3>'
            '<a class="back" href="#charts">Back to charts</a>'
            '</div>'
        )

        # Affected actions panel — slot in above the table when the category
        # actually has identifiable action refs (e.g. Node 20 deprecation has
        # them; `set-output` / `save-state` / generic Errors don't).
        bucket_actions = affected_actions.get(label) or {}
        if bucket_actions:
            # Sort by workflow count desc, then ref asc
            ordered = sorted(bucket_actions.items(), key=lambda kv: (-len(kv[1]), kv[0]))
            parts.append('<div class="affected-actions">')
            parts.append('<h4>Affected actions</h4><ul>')
            for ref, wfs in ordered:
                n = len(wfs)
                rem_html, rem_cls = remediation_for(ref, action_status)
                # Tooltip lists the workflows; cap at 30 lines to keep the
                # browser tooltip readable for high-fanout actions like
                # `HT2-Labs/elucidat-get-changed-files@v1.0.0` (177 workflows).
                wfs_sorted = sorted(wfs, key=lambda w: (w["repo"].lower(), w["workflow_name"].lower()))
                if len(wfs_sorted) > 30:
                    head = wfs_sorted[:30]
                    extra = len(wfs_sorted) - 30
                    lines = [f'{w["repo"]} / {w["workflow_name"]}' for w in head]
                    lines.append(f'…and {extra} more')
                else:
                    lines = [f'{w["repo"]} / {w["workflow_name"]}' for w in wfs_sorted]
                tooltip = html.escape("\n".join(lines))
                parts.append(
                    '<li>'
                    f'<a class="ref" href="#{action_id(ref)}">{html.escape(ref)}</a>'
                    f'<span class="count" title="{tooltip}">'
                    f'· {n} workflow{"s" if n != 1 else ""} affected ·</span>'
                    f'<span class="remediation {rem_cls}">{rem_html}</span>'
                    '</li>'
                )
            parts.append('</ul></div>')

        parts.append('<table><thead><tr>'
                     '<th>Repository</th><th>Workflow</th><th>Path</th>'
                     '</tr></thead><tbody>')
        for row in rows:
            title_text = html.escape("\n\n".join(row["messages"]))
            href = "#" + entry_id(row["key"])
            run_url = row.get("run_url") or ""
            wf_name = html.escape(str(row["workflow_name"]))
            if run_url:
                wf_cell = (
                    f'<td class="wf-cell">'
                    f'<a class="run-link" href="{html.escape(run_url)}" '
                    f'title="View workflow run on GitHub" '
                    f'target="_blank" rel="noopener">'
                    f'{wf_name} <span class="run-arrow">&#8599;</span>'
                    f'</a></td>'
                )
            else:
                wf_cell = f'<td><a class="row-link" href="{href}">{wf_name}</a></td>'
            parts.append(
                f'<tr title="{title_text}">'
                f'<td><a class="row-link" href="{href}">{html.escape(row["repo"])}</a></td>'
                f'{wf_cell}'
                f'<td class="path"><a class="row-link" href="{href}">{html.escape(str(row["workflow_path"]))}</a></td>'
                f'</tr>'
            )
        parts.append('</tbody></table></section>')
    return "".join(parts)


def render_action_details(action_workflows, action_status=None):
    """Hidden `:target`-revealed table per unique action ref. Linked from the
    affected-actions panel. Reuses .category-detail styling for visual parity."""
    parts = []
    action_status = action_status or {}
    ordered = sorted(action_workflows.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    for ref, wfs in ordered:
        if not wfs:
            continue
        aid = action_id(ref)
        rem_html, rem_cls = remediation_for(ref, action_status)
        parts.append(f'<section class="category-detail action-detail" id="{aid}">')
        parts.append(
            '<div class="cat-head">'
            f'<h3>Affected by <code>{html.escape(ref)}</code>'
            f'<span class="muted">({len(wfs)} workflow run(s))</span></h3>'
            '<a class="back" href="#charts">Back to charts</a>'
            '</div>'
            f'<div class="action-remediation"><span class="remediation {rem_cls}">'
            f'{rem_html}</span></div>'
        )
        parts.append('<table><thead><tr>'
                     '<th>Repository</th><th>Workflow</th><th>Path</th>'
                     '</tr></thead><tbody>')
        for w in wfs:
            href = "#" + entry_id(w["key"])
            run_url = w.get("run_url") or ""
            wf_name = html.escape(w["workflow_name"])
            if run_url:
                wf_cell = (
                    f'<td class="wf-cell">'
                    f'<a class="run-link" href="{html.escape(run_url)}" '
                    f'title="View workflow run on GitHub" '
                    f'target="_blank" rel="noopener">'
                    f'{wf_name} <span class="run-arrow">&#8599;</span>'
                    f'</a></td>'
                )
            else:
                wf_cell = f'<td><a class="row-link" href="{href}">{wf_name}</a></td>'
            parts.append(
                f'<tr>'
                f'<td><a class="row-link" href="{href}">{html.escape(w["repo"])}</a></td>'
                f'{wf_cell}'
                f'<td class="path"><a class="row-link" href="{href}">{html.escape(w["workflow_path"])}</a></td>'
                f'</tr>'
            )
        parts.append('</tbody></table></section>')
    return "".join(parts)


def classify(msg):
    low = msg.lower()
    if "deprecat" in low:
        return "deprecation"
    if "error" in low or "fail" in low:
        return "error"
    return "warning"


def anchor_for(repo):
    return "r-" + "".join(c if c.isalnum() else "-" for c in repo)


def render(data, generated_at):
    by_repo = defaultdict(list)
    for key, entry in data.items():
        repo_full = key.rsplit("_", 1)[0] if "_" in key else key
        by_repo[repo_full].append((key, entry))

    total_workflows = len(data)
    total_messages = sum(len(e.get("annotation_messages", [])) for e in data.values())
    total_repos = len(by_repo)

    parts = [
        "<!doctype html>",
        '<html lang="en"><head>',
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>GitHub Actions Annotations Report</title>",
        f"<style>{CSS}</style>",
        "</head><body>",
        '<header id="top">',
        "<h1>GitHub Actions Annotations Report</h1>",
        f'<div class="meta">Generated {html.escape(generated_at)}</div>',
        "</header>",
        '<section class="summary">',
        f'<div class="tile"><div class="num">{total_repos}</div><div class="lab">Repos</div></div>',
        f'<div class="tile"><div class="num">{total_workflows}</div><div class="lab">Workflow runs</div></div>',
        f'<div class="tile"><div class="num">{total_messages}</div><div class="lab">Annotation messages</div></div>',
        "</section>",
    ]

    if not by_repo:
        parts.append('<div class="empty">No annotations.</div>')
        parts.append("</body></html>")
        return "".join(parts)

    bucket_slices, top_messages = compute_analytics(data)
    if bucket_slices or top_messages:
        parts.append('<section class="charts" id="charts">')
        if bucket_slices:
            parts.append(
                '<div class="chart-card">'
                '<h3>Workflow runs by category</h3>'
                '<div class="donut-wrap">'
                f'{donut_svg(bucket_slices)}'
                f'{legend_html(bucket_slices)}'
                '</div></div>'
            )
        if top_messages:
            parts.append(
                '<div class="chart-card">'
                '<h3>Top 10 recurring messages (by workflow count)</h3>'
                f'{bar_chart_svg(top_messages)}'
                '</div>'
            )
        parts.append('</section>')

    action_status = load_action_status()

    suites = load_suites()
    breakdowns = compute_suite_breakdowns(data, suites) if suites else []
    if breakdowns:
        parts.append(suites_html(breakdowns))
        for row in breakdowns:
            if not row["slices"]:
                continue
            parts.append(render_category_details(
                compute_category_detail(row["data"]),
                row["slices"],
                id_prefix=row["slug"],
                title_suffix=f' in {row["name"]}',
                affected_actions=compute_affected_actions(row["data"]),
                action_status=action_status,
            ))

    if bucket_slices:
        parts.append(render_category_details(
            compute_category_detail(data),
            bucket_slices,
            affected_actions=compute_affected_actions(data),
            action_status=action_status,
        ))

    # Per-action drill-down tables — clicked from the affected-actions panel.
    # Org-wide scope (all workflows affected by each action), not suite-scoped.
    parts.append(render_action_details(compute_action_workflows(data), action_status))

    parts.append(f'<nav class="toc"><h2>Repositories ({total_repos})</h2><ul>')
    for repo in sorted(by_repo):
        count = len(by_repo[repo])
        parts.append(
            f'<li><a href="#{anchor_for(repo)}">{html.escape(repo)}</a>'
            f' <span class="count">({count})</span></li>'
        )
    parts.append("</ul></nav>")

    parts.append("<main>")
    for repo in sorted(by_repo):
        entries = by_repo[repo]
        parts.append(f'<section class="repo" id="{anchor_for(repo)}">')
        parts.append(
            f'<h2>{html.escape(repo)}'
            f' <span class="badge">{len(entries)} workflow run(s)</span></h2>'
        )
        for key, entry in entries:
            wf_name = entry.get("workflow_name", "unknown")
            wf_path = entry.get("workflow_path", "")
            run_url = entry.get("run_url") or ""
            messages = entry.get("annotation_messages", []) or []
            parts.append(f'<div class="workflow" id="{entry_id(key)}">')
            if run_url:
                parts.append(
                    f'<h3><a class="run-link" href="{html.escape(run_url)}" '
                    f'title="View workflow run on GitHub" '
                    f'target="_blank" rel="noopener">'
                    f'{html.escape(str(wf_name))} '
                    f'<span class="run-arrow">&#8599;</span></a></h3>'
                )
            else:
                parts.append(f'<h3>{html.escape(str(wf_name))}</h3>')
            if wf_path:
                parts.append(f'<div class="path">{html.escape(str(wf_path))}</div>')
            parts.append('<ul class="messages">')
            for msg in messages:
                if msg is None:
                    continue
                cls = classify(str(msg))
                parts.append(f'<li class="{cls}">{html.escape(str(msg))}</li>')
            parts.append("</ul></div>")
        parts.append("</section>")
    parts.append("</main>")
    parts.append('<a class="to-top" href="#top" title="Back to top">&uarr;</a>')
    parts.append("</body></html>")
    return "".join(parts)


def main():
    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 else INPUT_DEFAULT
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else OUTPUT_DEFAULT

    if not in_path.exists():
        print(f"No {in_path}; run annotations.py first.")
        sys.exit(1)

    try:
        with in_path.open() as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Could not parse {in_path}: {e}")
        sys.exit(1)

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out_path.write_text(render(data, generated), encoding="utf-8")
    print(f"Wrote {out_path} ({out_path.stat().st_size:,} bytes)")
    print(f"[GHA_DEP_SUMMARY] {json.dumps(summary_for(data))}")


if __name__ == "__main__":
    main()
