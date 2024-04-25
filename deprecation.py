import subprocess
import json
import re
import csv
import repos as r
import params as p

# Initialise parameters
repos = r.repos
verbose_output = p.verbose_output
deprecation_warning = p.deprecation_warning
csv_file_path = p.csv_file_path

# Define the fieldnames for the CSV header
fieldnames = ["Repository Name", "Workflow Name", "Workflow Path", "Affected Actions"]

# Open the CSV file in append mode
with open(csv_file_path, mode='a', newline='') as file:
    writer = csv.DictWriter(file, fieldnames=fieldnames)

    # Check if the file is empty, if yes, write the header
    if file.tell() == 0:
        writer.writeheader()
    
    # Write the data for each workflow iteration
    for repo in repos:
        try:
            # Initialise active_workflows
            active_workflows = []

            # Retrieve all workflows for a repository
            workflows_cmd = f"gh api '/repos/{repo}/actions/workflows'"
            workflows_output = subprocess.check_output(workflows_cmd, shell=True)
            workflows_data = json.loads(workflows_output)

            # Iterate through each workflow, add the id to the active_workflows list if the path is not empty
            for workflow in workflows_data["workflows"]:
                if workflow["path"]:
                    active_workflows.append(workflow["id"])

            # Retrieve the most recent, successful, completed workflow
            for workflow in active_workflows:
                recent_workflow_cmd = f"gh api '/repos/{repo}/actions/workflows/{workflow}/runs?status=completed&conclusion=success&per_page=1&sort=created&direction=desc'"
                recent_workflow_output = subprocess.check_output(recent_workflow_cmd, shell=True)
                recent_workflow_data = json.loads(recent_workflow_output)

                if recent_workflow_data["workflow_runs"]:
                    # Get the first workflow run (most recent)
                    recent_workflow_run = recent_workflow_data["workflow_runs"][0]

                    # Define the following variables
                    check_suite_id = recent_workflow_run["check_suite_id"]
                    workflow_name = recent_workflow_run["name"]
                    workflow_path = recent_workflow_run["path"]
                    repository_name = recent_workflow_run["repository"]["name"]

                    # Print the above variables
                    if verbose_output:
                        print("Check Suite ID:", check_suite_id)

                    print("Workflow Name:", workflow_name)
                    print("Workflow Path:", workflow_path)
                    print("Repository Name:", repository_name)

                    # Retrieve Annotations data
                    annotation_urls_cmd = f"gh api '/repos/{repo}/check-suites/{check_suite_id}/check-runs'"
                    annotation_urls_output = subprocess.check_output(annotation_urls_cmd, shell=True)
                    annotation_urls_data = json.loads(annotation_urls_output)

                    # Retrieve Annotations URLs if annotations_count is greater than 0
                    annotation_urls = []
                    for check_run in annotation_urls_data.get("check_runs", []):
                        annotations_count = check_run.get("output", {}).get("annotations_count", 0)
                        if annotations_count > 0:
                            annotations_url = check_run.get("output", {}).get("annotations_url")
                            annotation_urls.append(annotations_url)

                    if verbose_output:
                        print("Annotation URLs:", annotation_urls)

                    # Retrieve Annotations Messages if annotation_level is a warning and unique
                    annotation_messages = []
                    for annotation_url in annotation_urls:
                        annotation_messages_cmd = f"gh api '{annotation_url}'"
                        annotation_messages_output = subprocess.check_output(annotation_messages_cmd, shell=True)
                        annotation_messages_data = json.loads(annotation_messages_output)

                        for annotation_data in annotation_messages_data:
                            if annotation_data.get("annotation_level") == "warning":
                                annotation_message = annotation_data.get("message")
                                if annotation_message not in annotation_messages:
                                    if annotation_message.startswith(deprecation_warning):
                                        annotation_messages.append(annotation_message)

                    if verbose_output:
                        print("Annotation Messages:", annotation_messages)

                    # Retrieve the affected actions using regular expression
                    affected_actions = []
                    for message in annotation_messages:
                        matches = re.findall(r'(?:[\w-]+\/[\w-]+)@[\w\d]+(?:\.[\w\d]+)*', message)
                        for match in matches:
                            if match not in affected_actions:
                                affected_actions.append(match)

                    print("Affected Actions:", affected_actions)
                    print()

                    # Write the data to the CSV file if there are affected actions
                    if affected_actions:
                        writer.writerow({
                            "Repository Name": repository_name,
                            "Workflow Name": workflow_name,
                            "Workflow Path": workflow_path,
                            "Affected Actions": affected_actions
                        })
        except:
            print(f'Failed to analyse GHA Annotations for {repo}.')
            print('Exiting program.')
            exit()
