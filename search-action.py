import subprocess
import json
import csv
import os
import sys
import repos as r
import params as p

# Ensure the action name is passed as an argument
if len(sys.argv) < 2:
    print("Usage: python search-action.py <action_name>")
    sys.exit(1)

# The GitHub Action name to search for
action_name = sys.argv[1]

# CSV Output File
output_csv = f"repos_with_{action_name.replace('/', '_')}.csv"

# Use existing repos
repos = r.repos
verbose_output = p.verbose_output

# Prepare CSV header
fieldnames = ["Repository Name", "Workflow Name", "Workflow Path"]

# Open CSV file to write results
with open(output_csv, mode='w', newline='') as file:
    writer = csv.DictWriter(file, fieldnames=fieldnames)
    writer.writeheader()

    for repo in repos:
        try:
            print(f"Checking repository: {repo}")

            # Get the list of workflows
            workflows_cmd = f"gh api '/repos/{repo}/contents/.github/workflows'"
            
            try:
                workflows_output = subprocess.check_output(workflows_cmd, shell=True, stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                print(f"No workflows found in {repo}. Skipping...")
                continue

            workflows = json.loads(workflows_output)

            for workflow in workflows:
                if workflow["type"] != "file" or not workflow["name"].endswith(".yml"):
                    continue

                workflow_path = workflow["path"]

                # Fetch the content of the workflow file
                content_cmd = f"gh api '/repos/{repo}/contents/{workflow_path}'"
                content_output = subprocess.check_output(content_cmd, shell=True)
                content_data = json.loads(content_output)

                # Decode the base64-encoded content
                import base64
                workflow_content = base64.b64decode(content_data["content"]).decode("utf-8")

                # Check if the workflow contains the specified action
                if action_name in workflow_content:
                    print(f"✅ Found '{action_name}' in {repo}/{workflow['name']}")

                    # Write to CSV
                    writer.writerow({
                        "Repository Name": repo,
                        "Workflow Name": workflow["name"],
                        "Workflow Path": workflow_path
                    })

        except Exception as e:
            print(f"Error checking {repo}: {e}")
            continue

print(f"\nResults saved to: {output_csv}")
