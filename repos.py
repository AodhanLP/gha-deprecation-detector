import gh_client
import params as p

repos = []


def fetch_repos(page):
    data = gh_client.get(
        f"/orgs/{p.org}/repos",
        params={"per_page": 100, "page": page, "sort": "full_name"},
    )
    for r in data:
        repos.append(r["full_name"])
    return data


page = 1
while True:
    data = fetch_repos(page)
    if len(data) < 100:
        break
    page += 1

print("Total number of repositories:", len(repos))
print()
print(repos)
