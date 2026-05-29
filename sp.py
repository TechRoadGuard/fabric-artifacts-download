import requests
import os
import json
import base64
import time
from msal import ConfidentialClientApplication

# =========================================================
# CONFIGURATION
# =========================================================

TENANT_ID = "<TENANT_ID>"
CLIENT_ID = "<CLIENT_ID>"
CLIENT_SECRET = "<CLIENT_SECRET>"

WORKSPACE_ID = "<WORKSPACE_ID>"

BASE_PATH = r"C:\Fabric_Artifacts"
NOTEBOOK_PATH = os.path.join(BASE_PATH, "notebooks")
PIPELINE_PATH = os.path.join(BASE_PATH, "pipelines")

# =========================================================
# AUTHENTICATION
# =========================================================

authority = f"https://login.microsoftonline.com/{TENANT_ID}"

app = ConfidentialClientApplication(
    client_id=CLIENT_ID,
    authority=authority,
    client_credential=CLIENT_SECRET
)

token_result = app.acquire_token_for_client(
    scopes=["https://api.fabric.microsoft.com/.default"]
)

if "access_token" not in token_result:
    raise Exception(token_result)

ACCESS_TOKEN = token_result["access_token"]

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# =========================================================
# CREATE FOLDERS
# =========================================================

os.makedirs(NOTEBOOK_PATH, exist_ok=True)
os.makedirs(PIPELINE_PATH, exist_ok=True)

# =========================================================
# COMMON POLL FUNCTION
# =========================================================

def wait_for_operation(operation_url):
    for _ in range(30):
        poll = requests.get(operation_url, headers=headers)
        poll.raise_for_status()

        data = poll.json()
        status = data.get("status")

        print(f"Status: {status}")

        if status == "Succeeded":
            return True, operation_url + "/result"
        elif status in ["Failed", "Cancelled"]:
            return False, None

        time.sleep(3)

    return False, None

# =========================================================
# NOTEBOOKS
# =========================================================

print("\n================ NOTEBOOKS ================\n")

notebook_list_url = f"https://api.fabric.microsoft.com/v1/workspaces/{WORKSPACE_ID}/notebooks"

response = requests.get(notebook_list_url, headers=headers)
response.raise_for_status()

notebooks = response.json().get("value", [])

print(f"Found {len(notebooks)} notebooks")

for nb in notebooks:

    nb_id = nb["id"]
    nb_name = nb["displayName"]

    print(f"\nDownloading notebook: {nb_name}")

    export_url = (
        f"https://api.fabric.microsoft.com/v1/workspaces/"
        f"{WORKSPACE_ID}/notebooks/{nb_id}/getDefinition?format=ipynb"
    )

    resp = requests.post(export_url, headers=headers)

    if resp.status_code == 202:
        op_url = resp.headers.get("Location")
        ok, result_url = wait_for_operation(op_url)

        if not ok:
            print(f"Failed notebook: {nb_name}")
            continue

        result = requests.get(result_url, headers=headers).json()

    elif resp.status_code == 200:
        result = resp.json()

    else:
        print(f"Notebook API failed: {nb_name}")
        continue

    definition = result.get("definition", {})
    parts = definition.get("parts", [])

    saved = False

    for part in parts:
        path = part.get("path", "")
        payload = part.get("payload")

        if path.endswith(".ipynb") and payload:

            content = base64.b64decode(payload)

            safe_name = nb_name.replace("/", "_").replace("\\", "_")

            file_path = os.path.join(NOTEBOOK_PATH, f"{safe_name}.ipynb")

            with open(file_path, "wb") as f:
                f.write(content)

            print(f"Saved notebook: {file_path}")
            saved = True
            break

    if not saved:
        print(f"No notebook payload: {nb_name}")

# =========================================================
# PIPELINES
# =========================================================

print("\n================ PIPELINES ================\n")

list_url = (
    f"https://api.fabric.microsoft.com/v1/workspaces/"
    f"{WORKSPACE_ID}/items?type=DataPipeline"
)

response = requests.get(list_url, headers=headers)
response.raise_for_status()

pipelines = response.json().get("value", [])

print(f"Found {len(pipelines)} pipelines")

for pl in pipelines:

    pl_id = pl["id"]
    pl_name = pl["displayName"]

    print(f"\nDownloading pipeline: {pl_name}")

    export_url = (
        f"https://api.fabric.microsoft.com/v1/workspaces/"
        f"{WORKSPACE_ID}/items/{pl_id}/getDefinition"
    )

    resp = requests.post(export_url, headers=headers)

    if resp.status_code == 202:

        op_url = resp.headers.get("Location")

        for _ in range(30):

            poll = requests.get(op_url, headers=headers)
            poll.raise_for_status()

            data = poll.json()
            status = data.get("status")

            print(f"Status: {status}")

            if status == "Succeeded":
                break
            elif status in ["Failed", "Cancelled"]:
                print("Pipeline export failed")
                break

            time.sleep(3)

        result_url = op_url + "/result"
        result = requests.get(result_url, headers=headers).json()

    elif resp.status_code == 200:
        result = resp.json()

    else:
        print(f"Pipeline export failed: {resp.text}")
        continue

    definition = result.get("definition", {})

    if not definition:
        print(f"No definition for {pl_name}")
        continue

    safe_name = pl_name.replace("/", "_").replace("\\", "_")

    file_path = os.path.join(PIPELINE_PATH, f"{safe_name}.json")

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(definition, f, indent=4)

    print(f"Saved pipeline: {file_path}")

print("\nALL NOTEBOOKS + PIPELINES BACKUP COMPLETED")