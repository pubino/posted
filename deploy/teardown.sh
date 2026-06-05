#!/bin/zsh

# Color tokens for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]✔${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]⚠${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]✘${NC} $1"; }

# Title
echo -e "${YELLOW}====================================================${NC}"
echo -e "${YELLOW}      Azure Teardown Script - Poster Portal         ${NC}"
echo -e "${YELLOW}====================================================${NC}"

ENV_FILE=".env.deploy"

if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
fi

RG_NAME="${RG_NAME:-"orfe-dept-azure-wmassey-group-posted-rg"}"

# Explicitly select active subscription
TARGET_SUB="orfe-dept-azure-wmassey-group"
log_info "Configuring active subscription to: '${TARGET_SUB}'..."
az account set --subscription "$TARGET_SUB"
if [ $? -ne 0 ]; then
    log_error "Failed to set subscription context to ${TARGET_SUB}. Exiting."
    exit 1
fi

# Check for non-interactive flag or CI/CD environment
FORCE_TEARDOWN=false
for arg in "$@"; do
    if [[ "$arg" == "--yes" || "$arg" == "-y" ]]; then
        FORCE_TEARDOWN=true
    fi
done

if [[ "$CI" == "true" || "$GITHUB_ACTIONS" == "true" ]]; then
    log_info "Running in CI/CD environment. Assuming confirmation."
    FORCE_TEARDOWN=true
fi

if [ "$FORCE_TEARDOWN" = "false" ]; then
    echo -e "${RED}WARNING: This action is destructive and irreversible.${NC}"
    echo -e "This will delete the Resource Group ${YELLOW}'${RG_NAME}'${NC} and ALL associated resources:"
    echo -e "  - Container Registry (ACR)"
    echo -e "  - App Service Plan"
    echo -e "  - Web App (FastAPI instance and the SQLite Database)"
    echo

    echo -n "Type 'yes' to confirm teardown of resources: "
    read confirmation

    if [ "$confirmation" != "yes" ]; then
        log_info "Teardown cancelled."
        exit 0
    fi
else
    log_warning "Bypassing interactive confirmation because --yes/-y flag was set or running in CI/CD."
fi

log_info "Initiating resource group deletion command in subscription '${TARGET_SUB}'..."
az group delete --name "$RG_NAME" --yes

if [ $? -eq 0 ]; then
    log_success "Azure resource group '${RG_NAME}' deletion initiated."
    if [ -f "$ENV_FILE" ]; then
        rm "$ENV_FILE"
        log_info "Cached deployment configuration '${ENV_FILE}' removed."
    fi
    echo -e "${GREEN}✔ Teardown completed successfully!${NC}"
else
    log_error "Failed to delete Resource Group. Please delete it manually in the Azure Portal."
fi
