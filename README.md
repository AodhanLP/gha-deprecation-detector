# gha-deprecation-detector
Automated Python script to detect GitHub Action Deprecation Warning messages across all repositories in an organisation, and exports the results to a CSV file.

There is also a script to detect a specific GitHub Action being used in workflows across all repositories in an organisation, and exports the results to a CSV file.

# Setup

## Checkout the code
- `git clone git@github.com:AodhanLP/gha-deprecation-detector.git`

## Download and install the GitHub CLI
- `brew install gh`

## Authenticate with a GitHub host
- `gh auth login`

## Download and install Python
- `brew install python@3.11`

## Create a params file
- `cp params-dist.py params.py`
- Update your params file appropriately.

## Run the deprecation script
- `python3.11 deprecation.py`

## Run the specific action script
- `python3.11 search-action.py actions/checkout`
