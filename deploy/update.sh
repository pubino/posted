#!/bin/zsh

# Color tokens for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Print helper functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]✔${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]⚠${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]✘${NC} $1"; }
log_step() { echo -e "\n${CYAN}=== $1 ===${NC}"; }

# Title
echo -e "${YELLOW}====================================================${NC}"
echo -e "${YELLOW}        Azure Update Script - Poster Portal         ${NC}"
echo -e "${YELLOW}====================================================${NC}"

ENV_FILE=".env.deploy"

if [ ! -f "$ENV_FILE" ]; then
    log_error "Deployment configurations (${ENV_FILE}) not found."
    log_error "Please run deploy/deploy.sh first to provision resource instances."
    exit 1
fi

# Load variables
source "$ENV_FILE"

# Explicitly select active subscription
TARGET_SUB="orfe-dept-azure-wmassey-group"
log_info "Configuring active subscription to: '${TARGET_SUB}'..."
az account set --subscription "$TARGET_SUB"
if [ $? -ne 0 ]; then
    log_error "Failed to set subscription context to ${TARGET_SUB}. Exiting."
    exit 1
fi

log_step "Loading configurations"
log_info "Resource Group: ${RG_NAME}"
log_info "Registry: ${ACR_NAME}"
log_info "Web App: ${APP_NAME}"

# Log in to ACR
log_step "Logging into Container Registry"
az acr login --name "$ACR_NAME"
if [ $? -ne 0 ]; then
    log_error "ACR login failed. Are you logged in via 'az login'?"
    exit 1
fi

# Rebuild container image in the cloud using ACR Tasks
log_step "Rebuilding Container Image in the Cloud"
ACR_SERVER="${ACR_NAME}.azurecr.io"
IMAGE_TAG="${ACR_SERVER}/posted:latest"

log_info "Running az acr build..."
az acr build --registry "$ACR_NAME" --image "posted:latest" .
if [ $? -ne 0 ]; then
    log_error "Azure ACR cloud build failed."
    exit 1
fi
log_success "Image updated successfully: ${IMAGE_TAG}"

# Restart Web App to force container pull
log_step "Restarting Azure Web App"
log_info "Triggering App Service reload for ${APP_NAME}..."
az webapp restart --name "$APP_NAME" --resource-group "$RG_NAME"
if [ $? -ne 0 ]; then
    log_error "Failed to restart Web App."
    exit 1
fi

log_success "Web App restarted."
echo -e "${GREEN}✔ Application updated successfully!${NC}"
echo -e "Web App URL: ${CYAN}https://${APP_NAME}.azurewebsites.net${NC}"
