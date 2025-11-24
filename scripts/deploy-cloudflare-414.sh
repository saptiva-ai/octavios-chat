#!/bin/bash
# ========================================
# CLOUDFLARE DEPLOYMENT SCRIPT - 414.SAPTIVA.COM
# ========================================
# Quick deployment with Cloudflare handling SSL
#
# Usage:
#   ./scripts/deploy-cloudflare-414.sh [options]
#
# Options:
#   --skip-build    Skip building images (use existing images)
#   --only-config   Only update configs, don't rebuild or redeploy containers
#   --fast          Fast mode: only recreate web/api, keep data services running
#
set -e
set -o pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DEMO_SERVER="jf@server.example.com"
DEMO_PATH="/home/jf/capital414-chat"

# Parse arguments
SKIP_BUILD=false
ONLY_CONFIG=false
FAST_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-build) SKIP_BUILD=true; shift ;;
        --only-config) ONLY_CONFIG=true; shift ;;
        --fast) FAST_MODE=true; shift ;;
        *) log_error "Unknown option: $1"; exit 1 ;;
    esac
done

log_info() { echo -e "${BLUE}ℹ${NC} $1"; }
log_success() { echo -e "${GREEN}✔${NC} $1"; }
log_warning() { echo -e "${YELLOW}▲${NC} $1"; }
log_error() { echo -e "${RED}✖${NC} $1"; }

step() {
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}$1${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

main() {
    echo ""
    echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  CLOUDFLARE DEPLOYMENT - 414.SAPTIVA.COM                     ║${NC}"
    echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    if [[ "$SKIP_BUILD" == "true" ]]; then
        log_warning "Skipping build (using existing images)"
    fi

    if [[ "$FAST_MODE" == "true" ]]; then
        log_warning "Fast mode: only recreating web/api containers"
    fi

    # Config-only mode
    if [[ "$ONLY_CONFIG" == "true" ]]; then
        step "Config Update Mode"
        log_info "Transferring configuration files only..."
        ssh "$DEMO_SERVER" "mkdir -p $DEMO_PATH/infra/nginx $DEMO_PATH/envs"
        scp infra/docker-compose.cloudflare.yml "$DEMO_SERVER:$DEMO_PATH/infra/"
        scp envs/.env.prod "$DEMO_SERVER:$DEMO_PATH/envs/"
        scp infra/nginx/nginx.414.cloudflare.conf "$DEMO_SERVER:$DEMO_PATH/infra/nginx/"
        log_success "Configuration updated"
        return 0
    fi

    # Step 1: Build images (unless skipped)
    if [[ "$SKIP_BUILD" == "false" ]]; then
        step "Step 1/5: Build Docker Images"

        # Load env vars for build args
        if [[ -f "envs/.env.prod" ]]; then
            export $(grep -v '^#' envs/.env.prod | grep -E 'NEXT_PUBLIC|APP_NAME|FEATURE' | xargs)
        fi

        log_info "Building API image..."
        docker build -f apps/api/Dockerfile -t octavios-api:latest --target production apps/api

        log_info "Building Web image with production variables..."
        # IMPORTANT: Do NOT include /api suffix - routes already include it
        docker build -f apps/web/Dockerfile \
            --build-arg NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-https://414.saptiva.com}" \
            --build-arg NEXT_PUBLIC_APP_NAME="${NEXT_PUBLIC_APP_NAME:-Saptiva Copilot OS - Capital 414}" \
            --build-arg NEXT_PUBLIC_MAX_FILE_SIZE_MB="${NEXT_PUBLIC_MAX_FILE_SIZE_MB:-50}" \
            --build-arg NEXT_PUBLIC_FEATURE_WEB_SEARCH="${NEXT_PUBLIC_FEATURE_WEB_SEARCH:-false}" \
            --build-arg NEXT_PUBLIC_FEATURE_DEEP_RESEARCH="${NEXT_PUBLIC_FEATURE_DEEP_RESEARCH:-false}" \
            --build-arg NEXT_PUBLIC_FEATURE_ADD_FILES="${NEXT_PUBLIC_FEATURE_ADD_FILES:-true}" \
            --build-arg NEXT_PUBLIC_FEATURE_GOOGLE_DRIVE="${NEXT_PUBLIC_FEATURE_GOOGLE_DRIVE:-false}" \
            --build-arg NEXT_PUBLIC_FEATURE_CANVAS="${NEXT_PUBLIC_FEATURE_CANVAS:-false}" \
            --build-arg NEXT_PUBLIC_FEATURE_AGENT_MODE="${NEXT_PUBLIC_FEATURE_AGENT_MODE:-false}" \
            --build-arg NEXT_PUBLIC_FEATURE_MIC="${NEXT_PUBLIC_FEATURE_MIC:-false}" \
            -t octavios-web:latest --target runner .

        log_success "Images built successfully"
    fi

    # Step 2: Export images
    step "Step 2/5: Export Images to Tar"

    log_info "Exporting images..."
    docker save octavios-api:latest octavios-web:latest | gzip > /tmp/capital414-images.tar.gz

    FILESIZE=$(du -h /tmp/capital414-images.tar.gz | cut -f1)
    log_success "Images exported: $FILESIZE"

    # Step 3: Transfer to server
    step "Step 3/5: Transfer to Server"

    log_info "Transferring images to $DEMO_SERVER..."
    scp /tmp/capital414-images.tar.gz "$DEMO_SERVER:/tmp/"

    log_success "Transfer complete"

    # Step 3.5: Transfer configuration files
    log_info "Transferring configuration files..."
    ssh "$DEMO_SERVER" "mkdir -p $DEMO_PATH/infra/nginx $DEMO_PATH/envs"

    scp infra/docker-compose.cloudflare.yml "$DEMO_SERVER:$DEMO_PATH/infra/"
    scp envs/.env.prod "$DEMO_SERVER:$DEMO_PATH/envs/"
    scp infra/nginx/nginx.414.cloudflare.conf "$DEMO_SERVER:$DEMO_PATH/infra/nginx/"

    log_success "Configuration files transferred"

    # Step 4: Load images on server
    step "Step 4/5: Load Images on Server"

    log_info "Loading images on server..."
    ssh "$DEMO_SERVER" "
        gunzip -c /tmp/capital414-images.tar.gz | docker load
        rm /tmp/capital414-images.tar.gz
    "

    log_success "Images loaded"

    # Step 5: Start services
    step "Step 5/5: Deploy Services"

    if [[ "$FAST_MODE" == "true" ]]; then
        log_info "Fast mode: recreating only web/api containers..."
        ssh "$DEMO_SERVER" "
            cd $DEMO_PATH
            docker compose --env-file envs/.env.prod -f infra/docker-compose.cloudflare.yml up -d --force-recreate --no-deps web api nginx
            echo 'Waiting for services to start...'
            sleep 15
            docker compose --env-file envs/.env.prod -f infra/docker-compose.cloudflare.yml ps
        "
    else
        log_info "Full deployment: restarting all services..."
        ssh "$DEMO_SERVER" "
            cd $DEMO_PATH
            mkdir -p data/mongodb data/redis data/minio logs/nginx infra/ssl
            docker compose --env-file envs/.env.prod -f infra/docker-compose.cloudflare.yml down 2>/dev/null || true
            docker compose --env-file envs/.env.prod -f infra/docker-compose.cloudflare.yml up -d
            echo 'Waiting for services to start...'
            sleep 15
            docker compose --env-file envs/.env.prod -f infra/docker-compose.cloudflare.yml ps
        "
    fi

    log_success "Services deployed"

    # Cleanup local tar
    rm -f /tmp/capital414-images.tar.gz

    # Summary
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  DEPLOYMENT COMPLETE                                          ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${BLUE}Domain:${NC}       https://414.saptiva.com"
    echo -e "${BLUE}Status:${NC}       Deployed (Cloudflare SSL)"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "  1. Configure Cloudflare SSL mode: ${GREEN}Full (strict)${NC}"
    echo "     Dashboard → SSL/TLS → Overview → Full (strict)"
    echo ""
    echo "  2. Verify deployment:"
    echo "     ${GREEN}make status-demo${NC}"
    echo "     ${GREEN}curl https://414.saptiva.com/health${NC}"
    echo ""
    echo "  3. Test in browser:"
    echo "     ${GREEN}https://414.saptiva.com${NC}"
    echo ""
}

main "$@"
