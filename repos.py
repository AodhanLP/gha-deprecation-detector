import subprocess
import json
import params as p

# Initialise repos
repos = []

# Define a function to fetch repositories from a specific page
def fetch_repos(page):
    repos_cmd = f"gh api '/orgs/{p.org}/repos?per_page=100&page={page}&sort=full_name'"
    repos_output = subprocess.check_output(repos_cmd, shell=True)
    repos_data = json.loads(repos_output)
    for repo in repos_data:
        repos.append(repo["full_name"])
    return repos_data

# Fetch repositories from each page until there are no more pages
page = 1
while True:
    repos_data = fetch_repos(page)
    if len(repos_data) < 100:
        break
    page += 1

print("Total number of repositories:", len(repos))
print()
print(repos)
