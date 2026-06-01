"""Probe upstream GitHub actions for Node 24 compatibility.

Reads `annotations.json`, extracts every `owner/name@ref` action reference,
dedupes by `owner/name`, then queries the GitHub API per action to determine
whether a Node-24-compatible release exists. Writes `action_status.json`
that `render_report.py` reads at render time to emit per-action remediation.

Scope: top-level action references only (those mentioned by the workflow
runner in its annotation). Transitive deps (action A internally using
action B) are out of scope — the runner doesn't expose them.

Runtime: ~30-60s for ~30 unique actions (~90 API calls). `gh_client.py`
handles 429/403 backoff automatically, so quota-exhausted runs pause and
resume rather than fail.

Output: action_status.json with per-action verdict — see the README's
"Tweaking the report" section, or the schema doc in the project plan.
"""
import base64
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import gh_client
from deprecation import ACTION_REGEX, NON_ACTION_OWNERS

INPUT_PATH  = Path("annotations.json")
OUTPUT_PATH = Path("action_status.json")
TMP_PATH    = Path("action_status.json.tmp")

INTERNAL_OWNERS = {"ht2-labs"}
MAX_WORKERS = 4

# Pull `runs.using: nodeXX` out of an action.yml body. Action manifests have
# exactly one `using:` field by convention, under `runs:`. A multi-line regex
# is enough — avoids adding PyYAML as a dep.
_USING_RE    = re.compile(r'^\s*using:\s*[\'"]?([\w-]+)[\'"]?\s*$', re.MULTILINE)
_MAJOR_RE    = re.compile(r'^v?(\d+)')
# Heuristic: catches `## Breaking Changes`, `BREAKING:`, `Breaking change` etc.
# in a release body. Not a substitute for reading the notes — the URL is always
# surfaced regardless so reviewers can verify.
_BREAKING_RE = re.compile(r'\b(?:breaking\s+changes?|BREAKING:)', re.IGNORECASE)


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def repo_key(full_path):
    """Strip subpath: 'actions/cache/restore' -> 'actions/cache'. The action
    lives in the same GitHub repo regardless of which sub-action is referenced."""
    parts = full_path.split("/")
    return "/".join(parts[:2]) if len(parts) >= 2 else full_path


def extract_action_refs(data):
    """Returns {owner/repo: [observed_pin, ...]} across the whole dataset.
    Multi-segment refs (e.g. `actions/cache/restore@v4`) collapse to their repo."""
    refs = {}
    for entry in data.values():
        for msg in (entry.get("annotation_messages") or []):
            if not msg:
                continue
            for ref in ACTION_REGEX.findall(msg):
                if "@" not in ref or "/" not in ref:
                    continue
                full_path, _, pin = ref.partition("@")
                if not full_path or not pin:
                    continue
                owner = full_path.split("/", 1)[0].lower()
                if owner in NON_ACTION_OWNERS:
                    continue
                refs.setdefault(repo_key(full_path), set()).add(pin)
    return {k: sorted(v) for k, v in refs.items()}


def _decode_content(payload):
    """GitHub contents API returns base64-encoded `content`; decode safely."""
    try:
        return base64.b64decode(payload.get("content", "") or "").decode("utf-8", errors="replace")
    except Exception:
        return ""


def _fetch_action_yml(owner_name, ref):
    """Try action.yml at the given ref, then action.yaml, then default branch."""
    for filename in ("action.yml", "action.yaml"):
        try:
            payload = gh_client.get(
                f"/repos/{owner_name}/contents/{filename}",
                params={"ref": ref} if ref else None,
            )
            text = _decode_content(payload)
            if text:
                return text
        except Exception:
            continue
    # Last resort: default branch (no ref)
    for filename in ("action.yml", "action.yaml"):
        try:
            payload = gh_client.get(f"/repos/{owner_name}/contents/{filename}")
            text = _decode_content(payload)
            if text:
                return text
        except Exception:
            continue
    return ""


def _parse_runtime(text):
    m = _USING_RE.search(text or "")
    return m.group(1).lower() if m else ""


def _suggested_pin(tag_name):
    if not tag_name:
        return ""
    m = _MAJOR_RE.match(tag_name)
    return f"v{m.group(1)}" if m else tag_name


def _pin_matches_latest(observed_pins, latest_tag):
    """True if any observed pin is on the same major version as latest_tag."""
    latest_major = _MAJOR_RE.match(latest_tag or "")
    if not latest_major:
        return False
    target = latest_major.group(1)
    for pin in observed_pins:
        m = _MAJOR_RE.match(pin)
        if m and m.group(1) == target:
            return True
    return False


def probe_one(owner_name, observed_pins):
    """Returns a status dict for a single owner/name."""
    base = {
        "current_pins_observed": observed_pins,
        "checked_at": _now_iso(),
    }
    owner = owner_name.split("/", 1)[0]
    if owner.lower() in INTERNAL_OWNERS:
        return {**base, "verdict": "internal"}

    # 1. Latest release
    try:
        release = gh_client.get(f"/repos/{owner_name}/releases/latest")
    except Exception as e:
        return {**base, "verdict": "probe_failed", "reason": f"releases/latest: {e}"}
    tag_name = release.get("tag_name", "")
    published_at = release.get("published_at", "")
    release_url = release.get("html_url", "")
    release_body = release.get("body") or ""
    notes_mention_breaking = bool(_BREAKING_RE.search(release_body))
    if not tag_name:
        return {**base, "verdict": "probe_failed", "reason": "no_tag"}

    # 2. action.yml at that tag
    text = _fetch_action_yml(owner_name, tag_name)
    runtime = _parse_runtime(text)
    suggested = _suggested_pin(tag_name)

    status = {
        **base,
        "latest_release": tag_name,
        "latest_release_date": published_at,
        "latest_release_url": release_url,
        "latest_action_yml_runtime": runtime or "unknown",
        "suggested_pin": suggested,
        "notes_mention_breaking": notes_mention_breaking,
    }

    if runtime in {"composite", "docker"}:
        status["verdict"] = "non_node_runtime"
    elif runtime == "node24":
        status["verdict"] = (
            "pin_already_node24"
            if _pin_matches_latest(observed_pins, tag_name)
            else "newer_node24_available"
        )
    elif runtime in {"node12", "node16", "node20"}:
        status["verdict"] = "latest_still_node20"
    else:
        status["verdict"] = "probe_failed"
        status["reason"] = f"unknown_runtime:{runtime or 'none'}"
    return status


def main():
    if not INPUT_PATH.exists():
        print(f"[probe] {INPUT_PATH} not found; run annotations.py first.", file=sys.stderr)
        sys.exit(1)

    remaining, limit, _ = gh_client.rate_limit()
    print(f"[probe] GitHub API rate limit: {remaining}/{limit} remaining")

    with INPUT_PATH.open() as f:
        data = json.load(f)

    refs = extract_action_refs(data)
    print(f"[probe] {len(refs)} unique actions to check")

    results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(probe_one, owner_name, pins): owner_name
            for owner_name, pins in refs.items()
        }
        done = 0
        total = len(futures)
        for fut in as_completed(futures):
            owner_name = futures[fut]
            done += 1
            try:
                results[owner_name] = fut.result()
            except Exception as e:
                results[owner_name] = {
                    "current_pins_observed": refs[owner_name],
                    "verdict": "probe_failed",
                    "reason": f"unhandled: {e}",
                    "checked_at": _now_iso(),
                }
            if done % 10 == 0 or done == total:
                print(f"[probe] {done}/{total} actions checked")

    output = {"generated_at": _now_iso(), "actions": results}

    with TMP_PATH.open("w") as f:
        json.dump(output, f, indent=2, sort_keys=True)
    os.replace(TMP_PATH, OUTPUT_PATH)
    print(f"[probe] wrote {OUTPUT_PATH} ({len(results)} entries)")

    # Verdict tally for quick eyeballing
    tally = {}
    for s in results.values():
        tally[s.get("verdict", "?")] = tally.get(s.get("verdict", "?"), 0) + 1
    print(f"[probe] verdicts: {tally}")


if __name__ == "__main__":
    main()
