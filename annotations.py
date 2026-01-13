from datetime import datetime
import subprocess
import json
import repos as r
import params as p

# Initialise parameters
repos = r.repos
verbose_output = p.verbose_output
annotation_json = {}
    
# Iterate through each of the orgs repositories
for repo in repos:
    counter = 0
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
                    print("Repository Name:", repo)

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

                # Retrieve Annotations Messages from each Annotations URL
                annotation_messages = []
                for annotation_url in annotation_urls:
                    annotation_messages_cmd = f"gh api '{annotation_url}'"
                    annotation_messages_output = subprocess.check_output(annotation_messages_cmd, shell=True)
                    annotation_messages_data = json.loads(annotation_messages_output)

                    # Extract each annotation message and add to the list
                    for annotation_data in annotation_messages_data:
                        annotation_messages.append(annotation_data.get("message"))

                if verbose_output:
                    print("Annotation Messages:", annotation_messages)

                # Remove duplicated annotations per run prior to putting into JSON
                master_list = list(dict.fromkeys(annotation_messages))

                # Write the data to JSON
                if annotation_messages:
                    counter += 1
                    annotation_json[repo + '_' + str(counter)] = {
                    "check_suite_id" : check_suite_id,
                    "workflow_name" : workflow_name,
                    "workflow_path" : workflow_path,
                    "repository_name" : repository_name,
                    "annotation_messages" : master_list
                    }

    except Exception as e:
        print(e)

json_output = json.dumps(annotation_json, indent=4)
now = datetime.today().strftime('%d_%m_%Y_%H:%M:%S')

with open(f"data_{now}.json", "a") as j:
    j.write(json_output)
j.close()