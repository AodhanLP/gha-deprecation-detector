import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import gh_client
import params as p
import repos as r

MAX_WORKERS = 8
IGNORE_ACTORS = {"copilot", "renovate[bot]", "ht2bot", "dependabot[bot]"}

repos_list = r.repos
verbose_output = p.verbose_output
json_filename = p.json_filename


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
    if run.get("actor", {}).get("login", "").lower() in IGNORE_ACTORS:
        return None

    check_suite_id = run["check_suite_id"]
    workflow_name = run["name"]
    workflow_path = run["path"]
    repository_name = run["repository"]["name"]

    if verbose_output:
        print(f"[annotations] {repo} / {workflow_name} (suite {check_suite_id})")

    check_runs_data = gh_client.get(
        f"/repos/{repo}/check-suites/{check_suite_id}/check-runs"
    )
    annotation_urls = []
    for cr in check_runs_data.get("check_runs", []):
        out = cr.get("output") or {}
        if out.get("annotations_count", 0) > 0 and out.get("annotations_url"):
            annotation_urls.append(out["annotations_url"])

    messages = []
    for url in annotation_urls:
        for ann in gh_client.get(url):
            msg = ann.get("message")
            if msg:
                messages.append(msg)

    if not messages:
        return None
    return {
        "repo": repo,
        "check_suite_id": check_suite_id,
        "workflow_name": workflow_name,
        "workflow_path": workflow_path,
        "repository_name": repository_name,
        "annotation_messages": list(dict.fromkeys(messages)),
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
                print(f"[annotations] {repo}: failed to list workflows ({exc})")
                failures.append(("list_workflows", repo, None, exc))
                continue
            for wid in fut.result():
                repo_workflows.append((repo, wid))
        print(f"Scanning {len(repo_workflows)} workflows across {len(repos_list)} repos")

        proc_futures = {
            pool.submit(process_workflow, repo, wid): (repo, wid)
            for repo, wid in repo_workflows
        }

        annotation_json = {}
        counters = {}
        done = 0
        total = len(proc_futures)
        for fut in as_completed(proc_futures):
            repo, wid = proc_futures[fut]
            done += 1
            if done % 50 == 0 or done == total:
                print(f"  ...processed {done}/{total}")
            exc = fut.exception()
            if exc is not None:
                print(f"[annotations] {repo} workflow {wid}: {exc}")
                failures.append(("process_workflow", repo, wid, exc))
                continue
            result = fut.result()
            if result is None:
                continue
            counters[repo] = counters.get(repo, 0) + 1
            key = f"{repo}_{counters[repo]}"
            annotation_json[key] = {
                "check_suite_id": result["check_suite_id"],
                "workflow_name": result["workflow_name"],
                "workflow_path": result["workflow_path"],
                "repository_name": result["repository_name"],
                "annotation_messages": result["annotation_messages"],
            }

    with open(json_filename, "w") as j:
        json.dump(annotation_json, j, indent=4)
    print(f"\nWrote {len(annotation_json)} entries to {json_filename}")
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
