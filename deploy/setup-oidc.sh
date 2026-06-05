#!/bin/zsh

# Color tokens for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Print helper functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]✔${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]⚠${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]✘${NC} $1"; }
log_step() { echo -e "\n${CYAN}=== $1 ===${NC}"; }

# Title
echo -e "${YELLOW}====================================================${NC}"
echo -e "${YELLOW}       Azure OIDC & GitOps Setup Script             ${NC}"
echo -e "${YELLOW}====================================================${NC}"

# Check dependencies
log_step "Checking local dependencies"
for cmd in az gh git; do
    if ! command -v $cmd &> /dev/null; then
        log_error "$cmd is not installed. Please install it to proceed."
        exit 1
    fi
done
log_success "All dependencies (az, gh, git) are installed."

# Verify Azure login
log_step "Verifying Azure Authentication"
az account show &> /dev/null
if [ $? -ne 0 ]; then
    log_error "Please run 'az login' first. Exiting."
    exit 1
fi
log_success "Logged into Azure account."

# Explicitly select active subscription
TARGET_SUB="orfe-dept-azure-wmassey-group"
log_info "Configuring active subscription to: '${TARGET_SUB}'..."
az account set --subscription "$TARGET_SUB"
if [ $? -ne 0 ]; then
    log_error "Failed to set subscription context to ${TARGET_SUB}. Exiting."
    exit 1
fi
log_success "Subscription context set to '${TARGET_SUB}'."

# Verify GitHub CLI login
log_step "Verifying GitHub CLI Authentication"
gh auth status &> /dev/null
if [ $? -ne 0 ]; then
    log_error "Please run 'gh auth login' to authenticate the GitHub CLI. Exiting."
    exit 1
fi
log_success "GitHub CLI authenticated."

# Get GitHub repository path dynamically
REPO_PATH=$(git config --get remote.origin.url | sed -E 's/.*github.com[:\/](.*)\.git/\1/' 2>/dev/null)
if [ -z "$REPO_PATH" ]; then
    REPO_PATH="pubino/posted"
    log_warning "Could not parse git remote url. Defaulting repository path to: ${REPO_PATH}"
else
    log_info "Detected GitHub Repository path: ${REPO_PATH}"
fi

# Load configuration
ENV_FILE=".env.deploy"
if [ ! -f "$ENV_FILE" ]; then
    log_error "Deployment configurations (${ENV_FILE}) not found."
    log_error "Please run './deploy/deploy.sh' first to initialize infrastructure parameters."
    exit 1
fi

log_info "Loading settings from ${ENV_FILE}..."
source "$ENV_FILE"

# Retrieve tenant and subscription
TENANT_ID=$(az account show --query tenantId -o tsv)
SUBSCRIPTION_ID=$(az account show --query id -o tsv)

# Retrieve Application and SP details dynamically
log_step "Retrieving or Provisioning deployment Service Principal"
SP_DISPLAY_NAME="orfe-dept-azure-wmassey-group-posted-deployer"
log_info "Searching for AD Application with display name: ${SP_DISPLAY_NAME}..."

APP_ID=$(az ad app list --display-name "$SP_DISPLAY_NAME" --query "[0].appId" -o tsv 2>/dev/null)
if [ -z "$APP_ID" ]; then
    log_info "AD Application not found. Provisioning application registry..."
    APP_ID=$(az ad app create --display-name "$SP_DISPLAY_NAME" --query appId -o tsv)
    if [ $? -ne 0 ]; then log_error "Failed to create AD App registration."; exit 1; fi
fi

SP_OBJECT_ID=$(az ad sp list --display-name "$SP_DISPLAY_NAME" --query "[0].id" -o tsv 2>/dev/null)
if [ -z "$SP_OBJECT_ID" ]; then
    log_info "Service Principal not found. Creating principal connection..."
    SP_OBJECT_ID=$(az ad sp create --id "$APP_ID" --query id -o tsv)
    if [ $? -ne 0 ]; then log_error "Failed to create AD Service Principal."; exit 1; fi
fi

log_success "Found Application Client ID: ${APP_ID}"
log_success "Found Service Principal Object ID: ${SP_OBJECT_ID}"

# Grant Service Principal Contributor permissions on the Resource Group scope
log_step "Granting Contributor Role to Service Principal"
RG_ID=$(az group show --name "$RG_NAME" --query id -o tsv 2>/dev/null)
if [ -z "$RG_ID" ]; then
    log_error "Resource Group '${RG_NAME}' does not exist. Run './deploy/deploy.sh' first."
    exit 1
fi
log_info "Assigning Contributor role on scope ${RG_NAME}..."
az role assignment create --assignee "$SP_OBJECT_ID" --role Contributor --scope "$RG_ID" &>/dev/null
log_success "Contributor role assignment active."

# 1. Create Federated Credentials for GitHub Actions OIDC
log_step "Configuring GitHub Actions OIDC Federated Credentials"
FC_NAME="github-actions-oidc"
FC_EXISTS=$(az ad app federated-credential list --id "$APP_ID" --query "[?name=='${FC_NAME}'].name" -o tsv 2>/dev/null)

if [ -n "$FC_EXISTS" ]; then
    log_info "Federated credential '${FC_NAME}' already exists. Recreating it to sync settings..."
    az ad app federated-credential delete --id "$APP_ID" --federated-credential-id-or-name "$FC_NAME" --yes &>/dev/null
fi

PARAMS_JSON=$(cat <<EOF
{
  "name": "github-actions-oidc",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:${REPO_PATH}:ref:refs/heads/main",
  "description": "Federated credential for GitHub Actions OIDC on main branch",
  "audiences": ["api://AzureADTokenExchange"]
}
EOF
)

log_info "Creating federated credential for repo: ${REPO_PATH}, branch: main..."
az ad app federated-credential create --id "$APP_ID" --parameters "$PARAMS_JSON"
if [ $? -ne 0 ]; then
    log_error "Failed to create federated credential."
    exit 1
fi
log_success "Federated credential '${FC_NAME}' created successfully."

# 2. Get ACR scope
ACR_ID=$(az acr show --name "$ACR_NAME" --resource-group "$RG_NAME" --query id -o tsv 2>/dev/null)
if [ -z "$ACR_ID" ]; then
    log_error "Could not find Azure Container Registry '${ACR_NAME}' in resource group '${RG_NAME}'."
    exit 1
fi

# 3. Grant deployment Service Principal AcrPush permissions on the ACR
log_step "Configuring ACR push permissions for deployment Service Principal"
log_info "Assigning AcrPush role to Service Principal..."
az role assignment create --assignee "$SP_OBJECT_ID" --role AcrPush --scope "$ACR_ID" &>/dev/null
log_success "AcrPush role assignment active."

# 4. Enable System-Assigned Managed Identity on Web App
log_step "Configuring Web App Managed Identity container pull permissions"
log_info "Verifying identity on app service '${APP_NAME}'..."
az webapp identity assign --name "$APP_NAME" --resource-group "$RG_NAME" &>/dev/null

WEBAPP_PRINCIPAL_ID=$(az webapp identity show --name "$APP_NAME" --resource-group "$RG_NAME" --query principalId -o tsv 2>/dev/null)
if [ -z "$WEBAPP_PRINCIPAL_ID" ]; then
    log_error "Failed to retrieve Web App System-Assigned Principal ID."
    exit 1
fi

log_info "Assigning AcrPull role to Web App Managed Identity..."
az role assignment create --assignee "$WEBAPP_PRINCIPAL_ID" --role AcrPull --scope "$ACR_ID" &>/dev/null
log_success "AcrPull role assignment configured."

# 5. Configure GitHub Actions Variables & Secrets
log_step "Updating GitHub Repository Variables & Secrets"
log_info "Setting repository variables via GitHub CLI..."

gh variable set AZURE_CLIENT_ID --body "$APP_ID" --repo "$REPO_PATH"
gh variable set AZURE_TENANT_ID --body "$TENANT_ID" --repo "$REPO_PATH"
gh variable set AZURE_SUBSCRIPTION_ID --body "$SUBSCRIPTION_ID" --repo "$REPO_PATH"
gh variable set ACR_NAME --body "$ACR_NAME" --repo "$REPO_PATH"
gh variable set AZURE_APP_NAME --body "$APP_NAME" --repo "$REPO_PATH"

log_success "GitHub variables configured!"

# 6. Restart Web App to bind settings
log_step "Restarting Web App"
log_info "Restarting '${APP_NAME}' to reload pull configurations..."
az webapp restart --name "$APP_NAME" --resource-group "$RG_NAME"
log_success "Web App restarted successfully."

echo -e "\n${GREEN}✔ Setup Complete!${NC}"
echo -e "Your GitOps pipeline is now ready:"
echo -e "  - GitHub Actions uses passwordless OIDC to authenticate."
echo -e "  - Container images will build, push, and pull securely via Managed Identity."
echo -e "  - All configuration variables have been saved to your GitHub repo."
