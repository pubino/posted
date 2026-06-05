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
echo -e "${YELLOW}    Azure Deployment Script - Poster Portal         ${NC}"
echo -e "${YELLOW}====================================================${NC}"

# Check dependencies
log_step "Checking local dependencies"
for cmd in az; do
    if ! command -v $cmd &> /dev/null; then
        log_error "$cmd is not installed. Please install the Azure CLI to proceed."
        exit 1
    fi
done
log_success "All dependencies (az) are installed."

# Check Azure Login Status
log_step "Verifying Azure Authentication"
az account show &> /dev/null
if [ $? -ne 0 ]; then
    log_warning "You are not logged into Azure CLI. Running 'az login'..."
    az login
    if [ $? -ne 0 ]; then
        log_error "Failed to log in to Azure. Exiting."
        exit 1
    fi
fi
log_success "Logged into Azure account."

# Explicitly select active subscription
TARGET_SUB="orfe-dept-azure-wmassey-group"
log_info "Configuring active subscription to: '${TARGET_SUB}'..."
az account set --subscription "$TARGET_SUB"
if [ $? -ne 0 ]; then
    log_error "Failed to set subscription to ${TARGET_SUB}. Ensure you have access."
    exit 1
fi
log_success "Subscription context set to '${TARGET_SUB}'."

# Load configuration if exists
ENV_FILE=".env.deploy"
if [ -f "$ENV_FILE" ]; then
    log_info "Loading previously entered settings from ${ENV_FILE}..."
    source "$ENV_FILE"
fi

save_configs() {
    cat <<EOF > "$ENV_FILE"
RANDOM_ID="$RANDOM_ID"
RG_NAME="$RG_NAME"
LOCATION="$LOCATION"
ACR_NAME="$ACR_NAME"
PLAN_NAME="$PLAN_NAME"
APP_NAME="$APP_NAME"
DRUPAL_WEBHOOK_TOKEN="$DRUPAL_WEBHOOK_TOKEN"
TARGET_HOST="$TARGET_HOST"
EOF
}

log_step "Configuration Settings"
echo -e "${YELLOW}Press [Enter] to keep the default or previously entered value shown in brackets.${NC}"

# Unique suffix to avoid resource name collisions
if [ -z "$RANDOM_ID" ]; then
    RANDOM_ID=$(head /dev/urandom | LC_ALL=C tr -dc a-z0-9 | head -c 6 ; echo '')
    save_configs
fi

# 1. Azure Infrastructure Configs
RG_NAME_DEFAULT=${RG_NAME:-"orfe-dept-azure-wmassey-group-posted-rg"}
echo -n "Enter Azure Resource Group Name [$RG_NAME_DEFAULT]: "
read input
RG_NAME=${input:-$RG_NAME_DEFAULT}
save_configs

LOCATION_DEFAULT=${LOCATION:-"eastus"}
echo -n "Enter Azure Location [$LOCATION_DEFAULT]: "
read input
LOCATION=${input:-$LOCATION_DEFAULT}
save_configs

ACR_NAME_DEFAULT=${ACR_NAME:-"orfepostedacr${RANDOM_ID}"}
echo -n "Enter Azure Container Registry (ACR) Name [$ACR_NAME_DEFAULT]: "
read input
ACR_NAME=${input:-$ACR_NAME_DEFAULT}
ACR_NAME=$(echo "$ACR_NAME" | tr -cd '[:alnum:]' | tr '[:upper:]' '[:lower:]')
save_configs

PLAN_NAME_DEFAULT=${PLAN_NAME:-"orfe-posted-plan"}
echo -n "Enter Azure App Service Plan Name [$PLAN_NAME_DEFAULT]: "
read input
PLAN_NAME=${input:-$PLAN_NAME_DEFAULT}
save_configs

APP_NAME_DEFAULT=${APP_NAME:-"orfe-posted-app-${RANDOM_ID}"}
echo -n "Enter Azure Web App Name [$APP_NAME_DEFAULT]: "
read input
APP_NAME=${input:-$APP_NAME_DEFAULT}
APP_NAME=$(echo "$APP_NAME" | tr -cd '[:alnum:]-' | tr '[:upper:]' '[:lower:]')
save_configs

# 2. Application Configs
if [ -z "$DRUPAL_WEBHOOK_TOKEN" ]; then
    DRUPAL_WEBHOOK_TOKEN=$(head /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9' | head -c 16 ; echo '')
fi
echo -n "Enter Drupal Webhook Secret Token [$DRUPAL_WEBHOOK_TOKEN]: "
read input
DRUPAL_WEBHOOK_TOKEN=${input:-$DRUPAL_WEBHOOK_TOKEN}
save_configs

TARGET_HOST_DEFAULT=${TARGET_HOST:-"https://caarms.princeton.edu"}
echo -n "Enter Primary Target Site (for asset syncing) [$TARGET_HOST_DEFAULT]: "
read input
TARGET_HOST=${input:-$TARGET_HOST_DEFAULT}
save_configs

log_success "Deployment configurations saved and verified."

# Execute Pipeline
log_step "Deploying Azure Infrastructure"

# 1. Create Resource Group
log_info "Creating Resource Group: ${RG_NAME}..."
az group create --name "$RG_NAME" --location "$LOCATION"
if [ $? -ne 0 ]; then log_error "Failed to create Resource Group."; exit 1; fi
log_success "Resource Group '${RG_NAME}' ready."

# 2. Create Azure Container Registry
log_info "Creating Azure Container Registry: ${ACR_NAME}..."
az acr show --resource-group "$RG_NAME" --name "$ACR_NAME" &> /dev/null
if [ $? -ne 0 ]; then
    az acr create --resource-group "$RG_NAME" --name "$ACR_NAME" --sku Basic --admin-enabled false
    if [ $? -ne 0 ]; then log_error "Failed to create Container Registry."; exit 1; fi
else
    log_info "Container Registry '${ACR_NAME}' already exists. Ensuring admin login is disabled..."
    az acr update --name "$ACR_NAME" --resource-group "$RG_NAME" --admin-enabled false &>/dev/null
fi
log_success "Container Registry '${ACR_NAME}' ready."

# Get ACR server URL
ACR_SERVER="${ACR_NAME}.azurecr.io"
IMAGE_TAG="${ACR_SERVER}/posted:latest"

# 3. Build & Publish Image to Registry via cloud build (ACR Tasks)
log_info "Building container image in the cloud using Azure Container Registry (ACR Tasks)..."
az acr build --registry "$ACR_NAME" --image "posted:latest" .
if [ $? -ne 0 ]; then log_error "Azure ACR cloud build failed."; exit 1; fi
log_success "Cloud build complete and image stored in ACR: ${IMAGE_TAG}"

# 4. Provision App Service Plan (Basic Linux Plan supports CNAME mappings)
log_info "Creating App Service Plan: ${PLAN_NAME}..."
az appservice plan show --name "$PLAN_NAME" --resource-group "$RG_NAME" &> /dev/null
if [ $? -ne 0 ]; then
    az appservice plan create --name "$PLAN_NAME" --resource-group "$RG_NAME" --location "$LOCATION" --is-linux --sku B1
    if [ $? -ne 0 ]; then log_error "Failed to create App Service Plan."; exit 1; fi
fi
log_success "App Service Plan ready."

# 5. Provision Web App
log_info "Creating Web App: ${APP_NAME}..."
az webapp show --name "$APP_NAME" --resource-group "$RG_NAME" &> /dev/null
if [ $? -ne 0 ]; then
    az webapp create --resource-group "$RG_NAME" --plan "$PLAN_NAME" --name "$APP_NAME" --deployment-container-image-name "$IMAGE_TAG"
    if [ $? -ne 0 ]; then log_error "Failed to create Web App."; exit 1; fi
fi
log_success "Web App container instance provisioned."

# Configure container pull details using Managed Identity
log_info "Enabling system-assigned Managed Identity on Web App..."
az webapp identity assign --name "$APP_NAME" --resource-group "$RG_NAME" &>/dev/null
if [ $? -ne 0 ]; then log_error "Failed to enable Managed Identity on Web App."; exit 1; fi

WEBAPP_PRINCIPAL_ID=$(az webapp identity show --name "$APP_NAME" --resource-group "$RG_NAME" --query principalId -o tsv)
ACR_ID=$(az acr show --name "$ACR_NAME" --resource-group "$RG_NAME" --query id -o tsv)

log_info "Assigning AcrPull role to Web App Managed Identity..."
az role assignment create --assignee "$WEBAPP_PRINCIPAL_ID" --role AcrPull --scope "$ACR_ID" &>/dev/null

log_info "Configuring Web App settings (Managed Identity pull, Always On, and Persistent Storage)..."
# Setting acrUseManagedIdentityCreds to true allows the Web App to pull container images from ACR securely
# Setting WEBSITES_ENABLE_APP_SERVICE_STORAGE to true mounts a persistent network share for our SQLite database
az webapp config set --resource-group "$RG_NAME" --name "$APP_NAME" \
  --generic-configurations '{"acrUseManagedIdentityCreds": true, "alwaysOn": true}'
if [ $? -ne 0 ]; then log_error "Failed to configure generic configurations."; exit 1; fi

az webapp config appsettings set --resource-group "$RG_NAME" --name "$APP_NAME" --settings \
  WEBSITES_ENABLE_APP_SERVICE_STORAGE=true
if [ $? -ne 0 ]; then log_error "Failed to enable persistent storage settings."; exit 1; fi

az webapp config container set --name "$APP_NAME" --resource-group "$RG_NAME" \
  --docker-custom-image-name "$IMAGE_TAG" \
  --docker-registry-server-url "https://${ACR_SERVER}"
if [ $? -ne 0 ]; then log_error "Failed to configure Container Registry server URL."; exit 1; fi

# 6. Configure App Service Environment parameters
log_info "Configuring App Service environment parameters..."
az webapp config appsettings set --resource-group "$RG_NAME" --name "$APP_NAME" --settings \
  DATABASE_URL="sqlite:////home/posted.db" \
  DEV_MODE=False \
  PORT=8000 \
  DRUPAL_WEBHOOK_TOKEN="$DRUPAL_WEBHOOK_TOKEN" \
  TARGET_HOST="$TARGET_HOST" \
  BYPASS_HEADER_NAME="x-wdsoit-bot-bypass" \
  BYPASS_HEADER_VALUE="true"
if [ $? -ne 0 ]; then log_error "Failed to set App Service application settings."; exit 1; fi

log_success "Deployment complete!"
echo -e "\n${GREEN}=== Next Steps ===${NC}"
echo -e "1. Secure webhook token in Drupal using: ${DRUPAL_WEBHOOK_TOKEN}"
echo -e "2. Your web app is live at: ${CYAN}https://${APP_NAME}.azurewebsites.net${NC}"
echo -e "3. To map posters.caarms.princeton.edu CNAME, configure custom domains in the Azure Portal or via Azure CLI."
echo -e "4. Run setup-oidc.sh to configure the GitOps workflow pipeline."
