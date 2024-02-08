import os
import re
import requests
import json
import traceback
import datetime
from datetime import date
from github import Github

RELEVANCE_API_KEY = os.environ["RELEVANCE_API_KEY"]
RELEVANCE_REGION = os.environ["RELEVANCE_REGION"]

os.makedirs("templates", exist_ok=True)
os.makedirs("archive", exist_ok=True)

# Create a date object for the current date
current_date = str(date.today())
current_timestamp = str(datetime.datetime.now())

def make_valid_ref_name(name):
    name = name.replace(" ", "-")
    name = re.sub(r"[^\w-]", "", name)
    return name

def clean_filename(f):
    return re.sub(r"[^\w\-_.]", "_", f["title"]).lower() + f'--{f["studio_id"]}.json'

def unclean_filename(f):
    return re.sub(r"[\-_.]", " ", f.split("--")[0]).title() 

def create_pr(credential, region, reference="default", datatype="tools"):
    templates_folder = f"templates/{reference}/{datatype}"
    archive_folder = f"archive/{reference}/{datatype}"
    os.makedirs(templates_folder, exist_ok=True)
    os.makedirs(archive_folder, exist_ok=True)

    if datatype == "tools":
        url = f"https://api-{region}.stack.tryrelevance.com/latest/studios/list"
        response = requests.get(
            url, 
            headers={"Authorization" : credential}, 
            params={
                "page_size" : 9999, 
                "filters" : '[{"field":"project","condition":"==","condition_value":"project_id","filter_type":"exact_match"}]'.replace("project_id", credential.split(":")[0])
            }
        )
    elif datatype == "agents":
        url = f"https://api-{region}.stack.tryrelevance.com/latest/agents/list"
        response = requests.get(
            url, 
            headers={"Authorization" : credential}, 
            params={
                "page_size" : 9999, 
                "filters" : [{"field":"project","condition":"==","condition_value":credential.split(":")[0],"filter_type":"exact_match"}]
            }
        )
        
    list_of_results = [r for r in response.json()['results'] if r['public'] ]
    gh = Github(os.environ["GITHUB_TOKEN"])
    repo = gh.get_repo(os.environ["GITHUB_REPOSITORY"])
    new_branch_name = f"feature/{make_valid_ref_name(current_timestamp)}"
    new_branch = repo.create_git_ref(
        ref=f"refs/heads/{new_branch_name}", 
        sha=repo.get_branch("main").commit.sha
    )
    current_list = []
    for obj in list_of_results:
        current_list.append(clean_filename(obj))

    # Check if the file requires archiving
    print(f"Checking for files to archive in {reference}")
    for file in os.listdir(templates_folder):
        if file not in current_list:
            filepath = f"{templates_folder}/{file}"
            archive_filepath = f"{archive_folder}/{file}"
            with open(filepath, "r") as f:
                content = f.read()
            archive_commit_message = f"Archiving | {unclean_filename(file)} | {file.split('--')[1]} | {current_date}"
            try:
                sha = repo.get_contents(filepath).sha
                os.rename(filepath, archive_filepath)
                repo.delete_file(filepath, archive_commit_message, sha, branch=new_branch_name)
                repo.create_file(archive_filepath, archive_commit_message, content, branch=new_branch_name)
            except Exception as e:
                traceback.print_exc()

    print(f"Looping through  {reference}")
    # Loop through the tools in the cloud
    for i, obj in enumerate(list_of_results):
        if "metrics" in obj: del obj["metrics"]
        if "update_date_" in obj: del obj["update_date_"]
        file = clean_filename(obj)
        filepath = f"{templates_folder}/{file}"
        file_exists = False
        if os.path.exists(filepath):
            file_exists = True
        with open(filepath, "w") as f:
            json.dump(obj, f, indent=4)
        with open(filepath, "r") as f:
            content = f.read()

        if file_exists:
            commit_message = f"Updating | {unclean_filename(file)} | {file.split('--')[1]} | {current_date}"
            try:
                sha = repo.get_contents(filepath).sha
                status = repo.update_file(filepath, commit_message, content, sha, branch=new_branch_name)
            except Exception as e:
                traceback.print_exc()
        else:
            commit_message = f"New | {unclean_filename(file)} | {file.split('--')[1]} | {current_date}"
            repo.create_file(filepath, commit_message, content, branch=new_branch_name)
    
    print("Making pull request")
    pull_request = repo.create_pull(
        title=f"{reference} | {current_date} changes", 
        body=f"{reference} | {current_date} changes", 
        head=new_branch_name, 
        base="main"
    )
    if pull_request.changed_files > 0:
        commit_message = f"{current_date} changes"
        pull_request.edit(body=commit_message)
    else:
        #close pull request
        pull_request.edit(state="closed")

    pull_request.merge()

create_pr(RELEVANCE_API_KEY, RELEVANCE_REGION, datatype="tools")
create_pr(RELEVANCE_API_KEY, RELEVANCE_REGION, datatype="agents")