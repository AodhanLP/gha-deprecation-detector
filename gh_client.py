import os
import subprocess
import threading
import time

import requests

_token = None
_token_lock = threading.Lock()

_pause_until = 0.0
_pause_lock = threading.Lock()

_session_local = threading.local()


def _resolve_token():
    global _token
    if _token:
        return _token
    with _token_lock:
        if _token:
            return _token
        tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not tok:
            try:
                tok = subprocess.check_output(
                    ["gh", "auth", "token"], text=True
                ).strip()
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                raise RuntimeError(
                    "No GitHub token found. Set GH_TOKEN/GITHUB_TOKEN or run `gh auth login`."
                ) from e
        _token = tok
        return _token


def _session():
    s = getattr(_session_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {_resolve_token()}",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        _session_local.session = s
    return s


def _wait_if_paused():
    while True:
        with _pause_lock:
            now = time.time()
            if _pause_until <= now:
                return
            wait = _pause_until - now
        time.sleep(wait + 0.1)


def _pause_for(seconds):
    global _pause_until
    with _pause_lock:
        _pause_until = max(_pause_until, time.time() + seconds)


def _maybe_backoff(response):
    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", "60"))
        print(f"[gh_client] 429 secondary rate limit; pausing {retry_after}s")
        _pause_for(retry_after)
        return True
    if response.status_code == 403:
        if response.headers.get("X-RateLimit-Remaining") == "0":
            reset = int(response.headers.get("X-RateLimit-Reset", "0"))
            wait = max(reset - int(time.time()), 1) + 1
            print(f"[gh_client] Primary rate limit exhausted; pausing {wait}s")
            _pause_for(wait)
            return True
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            wait = int(retry_after)
            print(f"[gh_client] 403 with Retry-After {wait}s; pausing")
            _pause_for(wait)
            return True
    return False


def get(path_or_url, params=None, max_retries=5):
    url = (
        path_or_url
        if path_or_url.startswith("http")
        else f"https://api.github.com{path_or_url}"
    )
    sess = _session()
    last = None
    for attempt in range(max_retries):
        _wait_if_paused()
        try:
            r = sess.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** attempt
            print(f"[gh_client] request error {e}; retry in {wait}s")
            time.sleep(wait)
            continue

        last = r
        if r.status_code == 200:
            return r.json()
        if _maybe_backoff(r):
            continue
        if r.status_code in (500, 502, 503, 504):
            wait = 2 ** attempt
            print(f"[gh_client] {r.status_code}; retry in {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()

    if last is not None:
        last.raise_for_status()
    raise RuntimeError(f"GET {url} failed after {max_retries} retries")


def rate_limit():
    data = get("/rate_limit")
    core = data["resources"]["core"]
    return core["remaining"], core["limit"], core["reset"]
