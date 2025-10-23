#!/bin/bash
################################################################################
# Interactive Environment Setup Script
#
# Creates .env file with secure defaults and user input for sensitive values.
# Supports both development and production environments.
#
# Usage:
#   ./scripts/interactive-env-setup.sh [development|production]
#
# Features:
#   - Auto-generates strong secrets (JWT, passwords)
#   - Validates user input
#   - Preserves existing values (with confirmation)
#   - No hardcoded secrets
#   - Idempotent (safe to run multiple times)
################################################################################

set -e  # Exit on error

# ============================================================================
# STATUS TAGS & FORMATTING
# ============================================================================
RED="✖ "
GREEN="✔ "
YELLOW="▲ "
BLUE="▸ "
CYAN="◆ "
BOLD=""
NC=""

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

print_header() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}$1${NC}"
}

print_error() {
    echo -e "${RED}$1${NC}" >&2
}

print_warning() {
    echo -e "${YELLOW}$1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

generate_secret() {
    # Generate cryptographically secure random string
    openssl rand -hex 32 2>/dev/null || echo "$(date +%s | sha256sum | head -c 64)"
}

generate_password() {
    # Generate strong password (24 characters, alphanumeric + symbols)
    openssl rand -base64 24 2>/dev/null | tr -d "=+/" | cut -c1-24 || echo "ChangeMe$(date +%s)"
}

slugify_project_name() {
    # Convert arbitrary project name into a docker-compose friendly slug
    local name="$1"
    local slug
    slug="$(echo "$name" | tr '[:upper:]' '[:lower:]')"
    # Replace non-alphanumeric characters with hyphen and normalize the result
    slug="$(echo "$slug" | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$$//; s/-{2,}/-/g')"
    if [ -z "$slug" ]; then
        slug="mychat"
    fi
    echo "$slug"
}

validate_email() {
    local email="$1"
    if [[ "$email" =~ ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
        return 0
    else
        return 1
    fi
}

validate_url() {
    local url="$1"
    if [[ "$url" =~ ^https?:// ]]; then
        return 0
    else
        return 1
    fi
}

# Remove ANSI escape codes from a string
# This prevents color codes from contaminating .env files
sanitize_value() {
    local value="$1"
    # Remove ANSI escape sequences (ESC[...m)
    echo "$value" | sed 's/\x1b\[[0-9;]*m//g'
}



prompt_yes_no() {
    local prompt="$1"
    local default="${2:-n}"

    if (whiptail --title "Confirmation" --yes-button "Yes" --no-button "No" --yesno "$prompt" 10 60);
    then
        return 0
    else
        return 1
    fi

}

whiptail_input() {
    local prompt="$1"
    local default="$2"
    whiptail --title "Input" --inputbox "$prompt" 10 60 "$default" 3>&1 1>&2 2>&3
}

whiptail_password() {
    local prompt="$1"
    local default="$2"
    whiptail --title "Password" --passwordbox "$prompt" 10 60 "$default" 3>&1 1>&2 2>&3
}

# ============================================================================
# MAIN CONFIGURATION
# ============================================================================

# Determine environment
ENVIRONMENT="${1:-development}"
if [ "$ENVIRONMENT" != "development" ] && [ "$ENVIRONMENT" != "production" ]; then
    print_error "Invalid environment. Use 'development' or 'production'."
    echo "Usage: $0 [development|production]"
    exit 1
fi

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENVS_DIR="$PROJECT_ROOT/envs"
ENV_FILE="$ENVS_DIR/.env"
ENV_LOCAL_FILE="$ENVS_DIR/.env.local"

if [ "$ENVIRONMENT" = "development" ]; then
    TEMPLATE_FILE="$ENVS_DIR/.env.local.example"
    TARGET_FILE="$ENV_LOCAL_FILE"
else
    TEMPLATE_FILE="$ENVS_DIR/.env.production.example"
    TARGET_FILE="$ENVS_DIR/.env.prod"
fi

# ============================================================================
# WELCOME & CHECKS
# ============================================================================

clear
print_header "▸ CopilotOS - Interactive Environment Setup"

echo -e "${BOLD}Environment:${NC} $ENVIRONMENT"
echo -e "${BOLD}Target File:${NC} $TARGET_FILE"
echo ""

# Check for required tools
if ! command -v openssl &> /dev/null; then
    print_warning "openssl not found. Using fallback for secret generation."
    sleep 1
fi

# Check if target file exists
EXISTING_VALUES=()
if [ -f "$TARGET_FILE" ]; then
    print_warning "File $TARGET_FILE already exists."
    if ! prompt_yes_no "Do you want to update it (existing values will be preserved)?"; then
        print_info "Aborted. No changes made."
        exit 0
    fi
    echo ""
    print_info "Loading existing values..."
    # shellcheck disable=SC1090
    source "$TARGET_FILE" 2>/dev/null || true
fi

# ============================================================================
# COLLECT CONFIGURATION
# ============================================================================

print_header "◆ Configuration"

# ──────────────────────────────────────────────────────────────────────────
# 1. BASIC CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────
echo -e "${BOLD}1. Basic Configuration${NC}"
echo ""

# No default - force user to provide a project name
while true; do
    PROJECT_DISPLAY_NAME=$(whiptail_input \
        "Project display name (REQUIRED - e.g., 'MyChat', 'Copilot OS')" \
        "${PROJECT_DISPLAY_NAME:-}")

    if [ -z "$PROJECT_DISPLAY_NAME" ]; then
        if ! prompt_yes_no "Project name is required. Do you want to enter it now?"; then
            print_error "Setup cannot continue without a project name."
            exit 1
        fi
    else
        break
    fi
done

print_success "Project name set to: $PROJECT_DISPLAY_NAME"

# Generate slug from project name
DEFAULT_COMPOSE_SLUG="$COMPOSE_PROJECT_NAME"
if [ -z "$DEFAULT_COMPOSE_SLUG" ]; then
    DEFAULT_COMPOSE_SLUG="$(slugify_project_name "$PROJECT_DISPLAY_NAME")"
fi

while true; do
    COMPOSE_PROJECT_NAME_INPUT=$(whiptail_input \
        "Docker Compose project slug (REQUIRED - lowercase, no spaces)" \
        "$DEFAULT_COMPOSE_SLUG")

    if [ -z "$COMPOSE_PROJECT_NAME_INPUT" ]; then
        if ! prompt_yes_no "Project slug is required. Do you want to enter it now?"; then
            print_error "Setup cannot continue without a project slug."
            exit 1
        fi
    else
        break
    fi
done

COMPOSE_PROJECT_NAME=$(slugify_project_name "$COMPOSE_PROJECT_NAME_INPUT")
if [ "$COMPOSE_PROJECT_NAME" != "$COMPOSE_PROJECT_NAME_INPUT" ]; then
    print_warning "Normalized compose project slug to: $COMPOSE_PROJECT_NAME"
else
    print_success "Compose project slug set to: $COMPOSE_PROJECT_NAME"
fi

echo ""

if [ "$ENVIRONMENT" = "production" ]; then
    DOMAIN=$(whiptail_input \
        "Server domain or IP" \
        "${DOMAIN:-localhost}")
else
    DOMAIN="localhost"
fi

echo ""

# ──────────────────────────────────────────────────────────────────────────
# 1.5. DEPLOYMENT CONFIGURATION (Production only)
# ──────────────────────────────────────────────────────────────────────────
if [ "$ENVIRONMENT" = "production" ]; then
    echo -e "${BOLD}1.5. Deployment Configuration${NC}"
    echo ""

    print_info "These settings are used by deployment scripts (make deploy-*, etc.)"
    echo ""

    PROD_SERVER_IP=$(whiptail_input \
        "Production server IP address" \
        "${PROD_SERVER_IP:-$DOMAIN}")

    PROD_SERVER_USER=$(whiptail_input \
        "SSH username for deployment" \
        "${PROD_SERVER_USER:-$(whoami)}")

    PROD_DEPLOY_PATH=$(whiptail_input \
        "Deployment path on server" \
        "${PROD_DEPLOY_PATH:-/opt/octavios-bridge}" \
        "PROD_DEPLOY_PATH")

    PROD_BACKUP_DIR=$(whiptail_input \
        "Backup directory on server" \
        "${PROD_BACKUP_DIR:-/opt/backups/octavios-production}" \
        "PROD_BACKUP_DIR")

    # Constructed values
    PROD_SERVER_HOST="${PROD_SERVER_USER}@${PROD_SERVER_IP}"
    DEPLOY_SERVER="${PROD_SERVER_HOST}"
    DEPLOY_PATH="${PROD_DEPLOY_PATH}"
    BACKUP_DIR="${PROD_BACKUP_DIR}"

    print_success "Deployment configuration set"
    echo ""
fi

echo ""

# ──────────────────────────────────────────────────────────────────────────
# 2. DATABASE CREDENTIALS
# ──────────────────────────────────────────────────────────────────────────
echo -e "${BOLD}2. Database Credentials${NC}"
echo ""

if [ -z "$MONGODB_PASSWORD" ] || [ "$MONGODB_PASSWORD" = "secure_password_change_me" ]; then
    print_info "Generating secure MongoDB password..."
    MONGODB_PASSWORD=$(generate_password)
    print_success "Generated: ${MONGODB_PASSWORD:0:8}...${MONGODB_PASSWORD: -4}"
else
    if prompt_yes_no "Use existing MongoDB password?"; then
        print_success "Using existing MongoDB password"
    else
        MONGODB_PASSWORD=$(generate_password)
        print_success "Generated new MongoDB password"
    fi
fi

# Default MongoDB username based on project slug
DEFAULT_MONGODB_USER="${COMPOSE_PROJECT_NAME}_user"
MONGODB_USER=$(whiptail_input \
    "MongoDB username" \
    "${MONGODB_USER:-$DEFAULT_MONGODB_USER}" \
    "MONGODB_USER")

if [ -z "$REDIS_PASSWORD" ] || [ "$REDIS_PASSWORD" = "redis_password_change_me" ]; then
    print_info "Generating secure Redis password..."
    REDIS_PASSWORD=$(generate_password)
    print_success "Generated: ${REDIS_PASSWORD:0:8}...${REDIS_PASSWORD: -4}"
else
    if prompt_yes_no "Use existing Redis password?"; then
        print_success "Using existing Redis password"
    else
        REDIS_PASSWORD=$(generate_password)
        print_success "Generated new Redis password"
    fi
fi

echo ""

# ──────────────────────────────────────────────────────────────────────────
# 3. SECURITY SECRETS
# ──────────────────────────────────────────────────────────────────────────
echo -e "${BOLD}3. Security Secrets${NC}"
echo ""

if [ -z "$JWT_SECRET_KEY" ] || [ "$JWT_SECRET_KEY" = "dev-jwt-secret-change-in-production" ]; then
    print_info "Generating JWT secret key (64 characters)..."
    JWT_SECRET_KEY=$(generate_secret)
    print_success "Generated secure JWT secret"
else
    if prompt_yes_no "Use existing JWT secret key?"; then
        print_success "Using existing JWT secret"
    else
        JWT_SECRET_KEY=$(generate_secret)
        print_success "Generated new JWT secret"
    fi
fi

if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "dev-secret-change-in-production" ]; then
    print_info "Generating application secret key (64 characters)..."
    SECRET_KEY=$(generate_secret)
    print_success "Generated secure application secret"
else
    if prompt_yes_no "Use existing application secret key?"; then
        print_success "Using existing application secret"
    else
        SECRET_KEY=$(generate_secret)
        print_success "Generated new application secret"
    fi
fi

echo ""

# ──────────────────────────────────────────────────────────────────────────
# 4. EXTERNAL API KEYS
# ──────────────────────────────────────────────────────────────────────────
echo -e "${BOLD}4. External API Keys${NC}"
echo ""

print_warning "SAPTIVA API key is REQUIRED for the application to work."
while true; do
    SAPTIVA_API_KEY=$(whiptail_password \
        "SAPTIVA API key" \
        "${SAPTIVA_API_KEY:-}")

    if [ -z "$SAPTIVA_API_KEY" ] || [ "$SAPTIVA_API_KEY" = "your-saptiva-api-key-here" ]; then
        print_error "SAPTIVA API key cannot be empty!"
        if ! prompt_yes_no "Do you want to enter it now?"; then
            print_warning "Skipping SAPTIVA API key. You'll need to set it manually later."
            SAPTIVA_API_KEY="your-saptiva-api-key-here"
            break
        fi
    else
        print_success "SAPTIVA API key set"
        break
    fi
done

SAPTIVA_BASE_URL=$(whiptail_input \
    "SAPTIVA base URL" \
    "${SAPTIVA_BASE_URL:-https://api.saptiva.com}")

echo ""
# Aletheia configuration skipped by default (deep research features are optional)
# To enable, manually edit the .env file and set ALETHEIA_BASE_URL and ALETHEIA_API_KEY
print_info "Aletheia configuration skipped (deep research is optional and disabled by default)."
ALETHEIA_BASE_URL="${ALETHEIA_BASE_URL:-https://aletheia.saptiva.ai}"
ALETHEIA_API_KEY="${ALETHEIA_API_KEY:-}"

echo ""

# ──────────────────────────────────────────────────────────────────────────
# 5. FRONTEND CONFIGURATION
# ──────────────────────────────────────────────────────────────────────────
echo -e "${BOLD}5. Frontend Configuration${NC}"
echo ""

if [ "$ENVIRONMENT" = "production" ]; then
    NEXT_PUBLIC_API_URL=$(whiptail_input \
        "API URL (frontend will connect to this)" \
        "http://${DOMAIN}:8001")

    NODE_ENV="production"
else
    NEXT_PUBLIC_API_URL="http://localhost:8001"
    NODE_ENV="development"
fi

print_success "Frontend configured"

echo ""

# ============================================================================
# GENERATE .ENV FILE
# ============================================================================

print_header "▸ Generating Configuration File"

# Create backup if file exists
if [ -f "$TARGET_FILE" ]; then
    BACKUP_FILE="${TARGET_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    cp "$TARGET_FILE" "$BACKUP_FILE"
    print_info "Backup created: $BACKUP_FILE"
fi

# Generate .env file
cat > "$TARGET_FILE" << EOF
# ============================================================================
# AUTO-GENERATED ENVIRONMENT CONFIGURATION
# ============================================================================
# Generated on: $(date '+%Y-%m-%d %H:%M:%S')
# Environment: $ENVIRONMENT
# DO NOT COMMIT THIS FILE TO VERSION CONTROL
# ============================================================================

# ============================================================================
# BASIC CONFIGURATION
# ============================================================================
PROJECT_DISPLAY_NAME=$PROJECT_DISPLAY_NAME
COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME
DOMAIN=$DOMAIN
NODE_ENV=$NODE_ENV

# ============================================================================
# DEPLOYMENT CONFIGURATION (Production)
# ============================================================================
$(if [ "$ENVIRONMENT" = "production" ]; then
cat << DEPLOY_CONF
PROD_SERVER_IP=$PROD_SERVER_IP
PROD_SERVER_USER=$PROD_SERVER_USER
PROD_SERVER_HOST=$PROD_SERVER_HOST
PROD_DEPLOY_PATH=$PROD_DEPLOY_PATH
PROD_BACKUP_DIR=$PROD_BACKUP_DIR

# Legacy variables (backward compatibility)
DEPLOY_SERVER=$DEPLOY_SERVER
DEPLOY_PATH=$DEPLOY_PATH
BACKUP_DIR=$BACKUP_DIR
DEPLOY_CONF
fi)

# ============================================================================
# FRONTEND CONFIGURATION
# ============================================================================
NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
NEXT_TELEMETRY_DISABLED=1

# Feature Flags
NEXT_PUBLIC_FEATURE_WEB_SEARCH=true
NEXT_PUBLIC_FEATURE_DEEP_RESEARCH=false
NEXT_PUBLIC_FEATURE_ADD_FILES=true
NEXT_PUBLIC_FEATURE_GOOGLE_DRIVE=false
NEXT_PUBLIC_FEATURE_CANVAS=false
NEXT_PUBLIC_FEATURE_AGENT_MODE=false
NEXT_PUBLIC_FEATURE_MIC=false

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================
MONGODB_USER=$MONGODB_USER
MONGODB_PASSWORD=$MONGODB_PASSWORD
MONGODB_DATABASE=$COMPOSE_PROJECT_NAME
MONGODB_PORT=27017

REDIS_PASSWORD=$REDIS_PASSWORD
REDIS_PORT=6379

# ============================================================================
# AUTHENTICATION / SECURITY
# ============================================================================
JWT_SECRET_KEY=$JWT_SECRET_KEY
SECRET_KEY=$SECRET_KEY
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
JWT_ALGORITHM=HS256

# ============================================================================
# EXTERNAL APIS
# ============================================================================
SAPTIVA_API_KEY=$SAPTIVA_API_KEY
SAPTIVA_BASE_URL=$SAPTIVA_BASE_URL
SAPTIVA_TIMEOUT=120
SAPTIVA_MAX_RETRIES=3

# Chat Configuration
CHAT_DEFAULT_MODEL=Saptiva Turbo
CHAT_ALLOWED_MODELS=Saptiva Turbo,Saptiva Cortex,Saptiva Ops,Saptiva Coder

# Aletheia (optional - disabled by default)
# Deep research features require Aletheia API key
# To enable: set ALETHEIA_API_KEY and DEEP_RESEARCH_KILL_SWITCH=false
ALETHEIA_BASE_URL=$ALETHEIA_BASE_URL
ALETHEIA_API_KEY=$ALETHEIA_API_KEY
ALETHEIA_TIMEOUT=120
ALETHEIA_MAX_RETRIES=3

# Deep Research Feature Flags (disabled by default)
DEEP_RESEARCH_KILL_SWITCH=true
DEEP_RESEARCH_ENABLED=false
DEEP_RESEARCH_AUTO=false

# ============================================================================
# DEVELOPMENT/PRODUCTION SETTINGS
# ============================================================================
DEBUG=$([ "$ENVIRONMENT" = "development" ] && echo "true" || echo "false")
LOG_LEVEL=$([ "$ENVIRONMENT" = "development" ] && echo "debug" || echo "info")
RATE_LIMIT_REQUESTS_PER_MINUTE=$([ "$ENVIRONMENT" = "development" ] && echo "1000" || echo "100")

# ============================================================================
# CORS & HOSTS
# ============================================================================
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000","http://$DOMAIN:3000"]
ALLOWED_HOSTS=["localhost","127.0.0.1","$DOMAIN","web","api"]

# ============================================================================
# OBSERVABILITY
# ============================================================================
OTEL_SERVICE_NAME=$COMPOSE_PROJECT_NAME-bridge-$ENVIRONMENT
OTEL_ENABLED=false
JAEGER_ENDPOINT=http://localhost:14268/api/traces

# ============================================================================
# PERFORMANCE (PRODUCTION)
# ============================================================================
WORKERS=4
MAX_CONNECTIONS=100
POOL_SIZE=20
STREAM_BACKPRESSURE_MAX=2000
STREAM_HEARTBEAT_INTERVAL_MS=3000
SSE_KEEP_ALIVE_TIMEOUT_MS=45000
EOF

# Set restrictive permissions
chmod 600 "$TARGET_FILE"

print_success "Configuration file created: $TARGET_FILE"

# Also create .env symlink for backward compatibility
if [ "$TARGET_FILE" = "$ENV_LOCAL_FILE" ]; then
    ln -sf .env.local "$ENVS_DIR/.env"
    print_success "Symlink created: .env -> .env.local"
fi

# ============================================================================
# VALIDATION
# ============================================================================

print_header "🔍 Validating Configuration"

# Check for ANSI codes in the file (corrupted variables)
if grep -q $'\033\[' "$TARGET_FILE"; then
    print_error "WARNING: ANSI color codes detected in config file!"
    print_error "This can cause Docker Compose failures."
    print_warning "Please run 'make reset' if services fail to start."
fi

# Validate Docker Compose can read the file
print_info "Checking Docker Compose configuration..."
if command -v docker &> /dev/null && command -v docker compose &> /dev/null; then
    cd "$PROJECT_ROOT"
    if docker compose -f infra/docker-compose.yml --env-file "$TARGET_FILE" config > /dev/null 2>&1; then
        print_success "Docker Compose can read configuration correctly"
    else
        print_warning "Docker Compose validation failed - check your configuration"
    fi
else
    print_warning "Docker not found - skipping validation"
fi

# Check critical variables are set
print_info "Validating required variables..."
VALIDATION_ERRORS=0

if [ "$MONGODB_PASSWORD" = "secure_password_change_me" ]; then
    print_error "MongoDB password not set properly"
    VALIDATION_ERRORS=$((VALIDATION_ERRORS + 1))
fi

if [ "$REDIS_PASSWORD" = "redis_password_change_me" ]; then
    print_error "Redis password not set properly"
    VALIDATION_ERRORS=$((VALIDATION_ERRORS + 1))
fi

if [ "$SAPTIVA_API_KEY" = "your-saptiva-api-key-here" ]; then
    print_warning "SAPTIVA API key not set - application will not work properly"
fi

if [ $VALIDATION_ERRORS -eq 0 ]; then
    print_success "All required variables are set"
else
    print_error "$VALIDATION_ERRORS validation errors found"
fi

# ============================================================================
# SUMMARY
# ============================================================================

print_header "✔ Setup Complete!"

echo -e "${BOLD}Configuration Summary:${NC}"
echo ""
echo -e "  ${CYAN}Environment:${NC}        $ENVIRONMENT"
echo -e "  ${CYAN}Project:${NC}            $PROJECT_DISPLAY_NAME ($COMPOSE_PROJECT_NAME)"
echo -e "  ${CYAN}Config File:${NC}        $TARGET_FILE"
echo -e "  ${CYAN}Domain:${NC}             $DOMAIN"
echo -e "  ${CYAN}API URL:${NC}            $NEXT_PUBLIC_API_URL"
echo -e "  ${CYAN}MongoDB User:${NC}       $MONGODB_USER"
echo -e "  ${CYAN}SAPTIVA API:${NC}        ${SAPTIVA_API_KEY:0:12}..."
echo ""

print_warning "Security Notes:"
echo "  • Secrets have been auto-generated"
echo "  • File permissions set to 600 (owner read/write only)"
echo "  • NEVER commit this file to version control"
echo "  • Keep these credentials secure"
echo ""

echo -e "${BOLD}Next Steps:${NC}"
echo ""
if [ "$ENVIRONMENT" = "development" ]; then
    echo "  1. Review the configuration:"
    echo -e "     ${GREEN}cat $TARGET_FILE${NC}"
    echo ""
    echo "  2. Start the development environment:"
    echo -e "     ${GREEN}make dev${NC}"
    echo ""
    echo "  3. Create a demo user:"
    echo -e "     ${GREEN}make create-demo-user${NC}"
    echo ""
    echo "  4. Access the application:"
    echo -e "     ${GREEN}http://localhost:3000${NC}"
else
    echo "  1. Review the configuration:"
    echo -e "     ${GREEN}cat $TARGET_FILE${NC}"
    echo ""
    echo "  2. Deploy to production:"
    echo -e "     ${GREEN}make deploy-clean${NC}"
    echo ""
    echo "  3. Verify deployment:"
    echo -e "     ${GREEN}make deploy-status${NC}"
fi

echo ""
print_success "Setup completed successfully!"
echo ""
