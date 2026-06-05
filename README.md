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
*   **Dynamic RSS Feed**: Produces and serves standard RSS 2.0 XML feeds at `/feed.xml` and `/rss.xml` containing visible presenters, ordered alphabetically by last name.

---

## RSS Feed Syndication

To syndicate poster presentations to external department sites or widgets, consume one of the public endpoints:
*   **RSS URL**: `https://posters.caarms.princeton.edu/feed.xml` (or `/rss.xml`)
*   **Ordering**: Alphabetical by presenter's last name.
*   **Content**: Each `<item>` contains the poster title, filtered URL (e.g. `/?presenter=uuid`), registration date, and a description containing the presenter name and faculty adviser (excluding the abstract).

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

To automatically stream registrations to both the public poster directory and the private nametags dashboard, you configure two separate Remote Post handlers:

### 1. Handler A: Poster Presenters Webhook (Public Directory)
Used to populate the public-facing poster presentations index.
*   **Webform Path**: Navigate to `/admin/structure/webform/manage/{webform_id}`.
*   **Action**: Click **Emails/Handlers** -> **Add handler** -> **Remote post**.
*   **Configurations**:
    *   **Title**: Poster Presenters Webhook
    *   **Completed URL**: `https://posters.caarms.princeton.edu/api/drupal-webhook` (or `http://localhost:8000/api/drupal-webhook` for local dev).
    *   **Updated URL**: `https://posters.caarms.princeton.edu/api/drupal-webhook` (to capture metadata edits in real time).
*   **Security (Advanced Settings)**: In the **Custom options** YAML text area, input the token header:
    ```yaml
    headers:
      X-Drupal-Webhook-Token: <your_drupal_webhook_token_secret>
    ```
*   **Submission Data**: Ensure the following Drupal form fields are checked to send in the payload:
    *   `registrant_name` (or separate `first_name` and `last_name` fields)
    *   `email_address` (or `email`/`mail`)
    *   `presenting_poster` (triggers public visibility if value evaluates to "Yes"/"1"/"true")
    *   `poster_title`
    *   `faculty_adviser_name`
    *   `poster_presentation_abstract`

### 2. Handler B: Registrants Nametags Webhook (Admin Portal)
Used to populate the complete attendee list for badge compilation and print sheets.
*   **Action**: Click **Emails/Handlers** -> **Add handler** -> **Remote post**.
*   **Configurations**:
    *   **Title**: Registrants Nametags Webhook
    *   **Completed URL**: `https://posters.caarms.princeton.edu/api/nametags-webhook` (or `http://localhost:8000/api/nametags-webhook` for local dev).
    *   **Updated URL**: `https://posters.caarms.princeton.edu/api/nametags-webhook` (to capture metadata/role modifications).
*   **Security (Advanced Settings)**: In the **Custom options** YAML text area, input the token header:
    ```yaml
    headers:
      X-Drupal-Webhook-Token: <your_nametags_webhook_token_secret>
    ```
*   **Submission Data**: Ensure the following Drupal form fields are checked to send in the payload:
    *   `registrant_name` (or separate `first_name` and `last_name` fields)
    *   `email_address` (or `email`/`mail`)
    *   `home_institution_or_organization`
    *   `attendee_status` (e.g. Speaker, Attendee, Organizer)
    *   `student` (e.g. Yes/No)
    *   `t_shirt_size`
    *   `presenting_poster`

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
