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

## Notes

- All scripts share `gh_client.py` — auth from `GH_TOKEN`/`GITHUB_TOKEN` env var
  first, then `gh auth token` as fallback. Parallel API calls with automatic
  back-off on rate-limit hits.
- Output files are overwritten on each run.
