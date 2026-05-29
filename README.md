# gha-deprecation-detector

Scans a GitHub org for workflow annotations (deprecation warnings, errors, etc.)
and turns them into a CSV or a self-contained HTML report.

## Setup (once)

```bash
brew install gh python              # if not already
gh auth login                      # auth as yourself, or set GH_TOKEN env var
pip install -r requirements.txt

cp params-dist.py params.py        # then edit `org` in params.py
```

## The scripts

| Script             | What it does                                                        | Output                       |
|--------------------|----------------------------------------------------------------------|------------------------------|
| `annotations.py`   | Wide net — collect every annotation message from the latest successful run of every workflow | `annotations.json`           |
| `deprecation.py`   | Narrow filter — only warnings matching `params.deprecation_warning`, extracts affected `owner/action@ref` | `affected_actions.csv`       |
| `search-action.py` | Find every workflow in the org that references a given action       | `repos_with_<action>.csv`    |
| `render_report.py` | Turn `annotations.json` into a styled HTML report (charts, tables)  | `annotations_report.html`    |

## Typical run

```bash
python3 annotations.py          # collect — takes a few minutes
python3 render_report.py        # render — instant
open annotations_report.html       # view
```

For the narrower spreadsheet of just deprecation hits:

```bash
python3 deprecation.py
open affected_actions.csv
```

To check which repos use a specific action:

```bash
python3 search-action.py actions/checkout
```

## Maintaining the report

Two JSON files at the repo root drive what shows up in the HTML report — edit
them, re-run `render_report.py`, done. No Python change needed.

| File | Controls | Add an entry when... |
|---|---|---|
| `buckets.json` | How annotation messages are categorised (donut slices, drill-down tables) | GitHub announces a new deprecation type — e.g. Node.js 24 deprecation |
| `suites.json`  | Which products belong to which suite ( "By suite" cards) | A new product joins a team, or a new suite is wanted |

**`buckets.json`** — list of `{label, pattern}`. Pattern is a lowercased
substring match; **order matters** (first match wins), so put specific
entries before generic ones. Anything that doesn't match falls into
`Other deprecation` / `Errors` / `Other warnings` automatically.

**`suites.json`** — object of `suite name → list of product names`.
Product names are matched against repo basenames after lowercasing and
stripping non-alphanumerics (`Design-System` matches repo `design-system`).
Repos not in any suite fall into `Other`.

## Notes

- All scripts share `gh_client.py` — auth from `GH_TOKEN`/`GITHUB_TOKEN` env var
  first, then `gh auth token` as fallback. Parallel API calls with automatic
  back-off on rate-limit hits.
- Output files are overwritten on each run.
