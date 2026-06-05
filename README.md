# Posted - CAARMS 2026 Poster Presenters Portal

A lightweight Python (FastAPI) web portal that collects and displays poster presenters' registration details (name, title, adviser, and abstract) in the exact layout, theme, and design of the primary site `caarms.princeton.edu`.

---

## Features

*   **Visual Mirroring**: Automatically downloads and matches the branding layout, headers, footers, typography, and Bootstrap stylesheets of `caarms.princeton.edu`.
*   **LaTeX Support**: Seamlessly renders inline LaTeX formulas (e.g. `$E=mc^2$`) in abstracts using MathJax.
*   **Cost-Efficient ($0 DB Cost)**: Relies on SQLite for both local development and production. Azure App Service persistent storage mounts keep data across deployments without the cost of a PostgreSQL cluster.
*   **Webform Remote Post Webhook**: Accepts webform submissions directly from Drupal 10, validating integrity with a custom header secret token.
*   **Bulk Import Utility**: Built-in CLI command tool imports pre-existing submissions exported from Drupal in JSON/CSV.
*   **Secret-less GitOps**: Deploys via GitHub Actions utilizing Azure Active Directory OIDC Federated Credentials and App Service system-assigned Managed Identities.

---

## Local Setup & Development

### 1. Requirements
Ensure you have Python 3.11 or Python 3.12 installed on your system.

### 2. Set Up Virtual Environment & Dependencies
```bash
# Navigate to the project folder
cd posted

# Create a virtual environment
python3 -m venv test_env

# Activate the virtual environment
source test_env/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 3. Run Development Server
```bash
# Start uvicorn with hot reload enabled
PYTHONPATH=. uvicorn backend.main:app --reload
```
Access the local site at: **`http://localhost:8000`**

### 4. Run Test Suite
To run the automated endpoint validation and database integrity checks:
```bash
# Run pytest
PYTHONPATH=. pytest -v
```

---

## Drupal 10 Remote Post Setup

To automatically stream registrations to the **posted** app:
1.  Navigate to your Drupal Webform: `/admin/structure/webform/manage/{webform_id}`.
2.  Click **Emails/Handlers** -> **Add handler** -> **Remote post**.
3.  Set the following settings:
    *   **Title**: Poster Presenters Webhook
    *   **Completed URL**: `https://posters.caarms.princeton.edu/api/drupal-webhook`
4.  Under the **Advanced** settings section, locate the **Custom options** text area and enter the header authentication token:
    ```yaml
    headers:
      X-Drupal-Webhook-Token: <your_secret_token>
    ```
5.  In the **Submission data** tab, ensure the fields are selected and mapped: `registrant_name`, `email_address`, `presenting_poster`, `poster_title`, `faculty_adviser_name`, `poster_presentation_abstract`, and `home_institution_or_organization`.
6.  Save the configuration.

---

## Handling Existing Submissions

Since the webhook only fires automatically on *new* submissions, any registrations created before configuring the webhook must be imported:

### Option A: Manual Admin Resubmit
1.  Navigate to `/admin/structure/webform/manage/{webform_id}/results/submissions`.
2.  For each poster submission, click **View** -> **Resubmit**.
3.  This triggers the remote post webhook, populating the presenter into the web app automatically.

### Option B: Bulk JSON Export Import (Recommended)
1.  Export existing submissions:
    *   Go to `/admin/structure/webform/manage/{webform_id}/results/download`.
    *   Select **JSON** format, check the relevant fields, and download the export file (e.g. `export.json`).
2.  Run the import script locally:
    ```bash
    python backend/import_existing.py /path/to/export.json
    ```
    The utility extracts entries matching `presenting_poster == 'Yes'`, parses the attributes, and upserts them directly into the SQLite database.

---

## Azure Hosting & GitOps Pipeline

### 1. Clean Infrastructure Provisioning
Provision the resource group, container registry, app plan, app instance, and configure active Azure settings:
```bash
# Run deployment script (sets active subscription context automatically)
./deploy/deploy.sh
```

### 2. Modern Secret-less GitOps Migration
Configure OpenID Connect (OIDC) authentication and bind repository settings for automated GitHub push deployments:
```bash
# Run setup script to configure AD app, federated credentials, and repo variables
./deploy/setup-oidc.sh
```

### 3. Destruction / Teardown
To teardown all resources and clean up the Azure environment:
```bash
# Run teardown script
./deploy/teardown.sh
```
