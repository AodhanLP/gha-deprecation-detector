import csv
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import gh_client
import params as p
import repos as r

MAX_WORKERS = 8
ACTION_REGEX = re.compile(r'(?:[\w-]+\/[\w-]+)@[\w\d]+(?:\.[\w\d]+)*')

repos_list = r.repos
verbose_output = p.verbose_output
deprecation_warning = p.deprecation_warning
csv_file_path = p.csv_file_path

fieldnames = ["Repository Name", "Workflow Name", "Workflow Path", "Affected Actions"]


def list_workflows(repo):
    data = gh_client.get(f"/repos/{repo}/actions/workflows")
    return [w["id"] for w in data.get("workflows", []) if w.get("path")]


def process_workflow(repo, workflow_id):
    runs_data = gh_client.get(
        f"/repos/{repo}/actions/workflows/{workflow_id}/runs",
        params={
            "status": "completed",
            "conclusion": "success",
            "per_page": 1,
            "sort": "created",
            "direction": "desc",
        },
    )
    runs = runs_data.get("workflow_runs", [])
    if not runs:
        return None
    run = runs[0]
    check_suite_id = run["check_suite_id"]
    workflow_name = run["name"]
    workflow_path = run["path"]
    repository_name = run["repository"]["name"]

    if verbose_output:
        print(f"[deprecation] {repo} / {workflow_name} (suite {check_suite_id})")

    check_runs_data = gh_client.get(
        f"/repos/{repo}/check-suites/{check_suite_id}/check-runs"
    )
    annotation_urls = []
    for cr in check_runs_data.get("check_runs", []):
        out = cr.get("output") or {}
        if out.get("annotations_count", 0) > 0 and out.get("annotations_url"):
            annotation_urls.append(out["annotations_url"])

    seen_messages = set()
    affected_actions = []
    for url in annotation_urls:
        for ann in gh_client.get(url):
            if ann.get("annotation_level") != "warning":
                continue
            msg = ann.get("message") or ""
            if msg in seen_messages or not msg.startswith(deprecation_warning):
                continue
            seen_messages.add(msg)
            for m in ACTION_REGEX.findall(msg):
                if m not in affected_actions:
                    affected_actions.append(m)

    if not affected_actions:
        return None
    return {
        "Repository Name": repository_name,
        "Workflow Name": workflow_name,
        "Workflow Path": workflow_path,
        "Affected Actions": affected_actions,
    }


def main():
    remaining, limit, reset = gh_client.rate_limit()
    print(f"GitHub API rate limit: {remaining}/{limit} remaining")
    if remaining < 200:
        wait_s = max(reset - int(time.time()), 0)
        print(f"WARNING: rate limit low. Resets in {wait_s}s")

    failures = []  # list of (stage, repo, workflow_id_or_None, exception)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        wf_futures = {pool.submit(list_workflows, repo): repo for repo in repos_list}
        repo_workflows = []
        for fut in as_completed(wf_futures):
            repo = wf_futures[fut]
            exc = fut.exception()
            if exc is not None:
                print(f"[deprecation] {repo}: failed to list workflows ({exc})")
                failures.append(("list_workflows", repo, None, exc))
                continue
            for wid in fut.result():
                repo_workflows.append((repo, wid))
        print(f"Scanning {len(repo_workflows)} workflows across {len(repos_list)} repos")

        proc_futures = {
            pool.submit(process_workflow, repo, wid): (repo, wid)
            for repo, wid in repo_workflows
        }
        rows = []
        done = 0
        total = len(proc_futures)
        for fut in as_completed(proc_futures):
            repo, wid = proc_futures[fut]
            done += 1
            if done % 50 == 0 or done == total:
                print(f"  ...processed {done}/{total}")
            exc = fut.exception()
            if exc is not None:
                print(f"[deprecation] {repo} workflow {wid}: {exc}")
                failures.append(("process_workflow", repo, wid, exc))
                continue
            result = fut.result()
            if result:
                rows.append(result)

    with open(csv_file_path, mode="w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"\nWrote {len(rows)} rows to {csv_file_path}")
    print(f"Failures: {len(failures)}")
    if failures:
        for stage, repo, wid, exc in failures[:20]:
            target = f"{repo} workflow {wid}" if wid is not None else repo
            print(f"  [{stage}] {target}: {exc}")
        if len(failures) > 20:
            print(f"  ...and {len(failures) - 20} more")
        sys.exit(1)


if __name__ == "__main__":
    main()
