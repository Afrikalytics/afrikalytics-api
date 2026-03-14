#!/usr/bin/env bash
###############################################################################
# rollback.sh — Rollback Afrikalytics deployments
#
# Usage:
#   ./scripts/rollback.sh [dashboard|api|all] [commit-hash]
#
# Requires:
#   - Vercel CLI (npx vercel) for dashboard rollback
#   - Railway CLI (npx @railway/cli) for API rollback
#   - curl for health checks
#
# Environment variables:
#   VERCEL_TOKEN       — Vercel API token
#   VERCEL_ORG_ID      — Vercel organization ID
#   VERCEL_PROJECT_ID  — Vercel project ID
#   RAILWAY_TOKEN      — Railway API token
#   API_URL            — API base URL for health check
#   DASHBOARD_URL      — Dashboard base URL for health check
###############################################################################
set -euo pipefail

# ---------------------------------------------------------------------------
# Colors and logging
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} ${CYAN}INFO${NC}  $*"; }
log_success() { echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} ${GREEN}OK${NC}    $*"; }
log_warn()    { echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} ${YELLOW}WARN${NC}  $*"; }
log_error()   { echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} ${RED}FAIL${NC}  $*"; }

# ---------------------------------------------------------------------------
# Paths and configuration
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

TARGET="${1:-all}"
COMMIT_HASH="${2:-}"

API_URL="${API_URL:-https://web-production-ef657.up.railway.app}"
DASHBOARD_URL="${DASHBOARD_URL:-https://afrikalytics.vercel.app}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-15}"

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
preflight() {
    log_info "Running pre-flight checks..."

    if [[ "$TARGET" == "dashboard" || "$TARGET" == "all" ]]; then
        if ! command -v npx &>/dev/null; then
            log_error "npx is not installed (required for Vercel CLI)"
            exit 1
        fi
    fi
}

# ---------------------------------------------------------------------------
# Health check helper
# ---------------------------------------------------------------------------
wait_for_health() {
    local name="$1"
    local url="$2"
    local max_attempts="${3:-12}"
    local delay="${4:-10}"

    log_info "Waiting for ${name} to become healthy (max ${max_attempts} attempts, ${delay}s interval)..."

    for ((i = 1; i <= max_attempts; i++)); do
        local http_code
        http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$HEALTH_TIMEOUT" "$url" 2>/dev/null) || true

        if [[ "$http_code" == "200" ]]; then
            log_success "${name} is healthy (HTTP ${http_code}) after attempt ${i}"
            return 0
        fi

        log_info "Attempt ${i}/${max_attempts}: HTTP ${http_code} — retrying in ${delay}s..."
        sleep "$delay"
    done

    log_error "${name} did not become healthy after ${max_attempts} attempts"
    return 1
}

# ---------------------------------------------------------------------------
# Rollback Dashboard (Vercel)
# ---------------------------------------------------------------------------
rollback_dashboard() {
    echo ""
    log_info "=== Rolling back Dashboard (Vercel) ==="
    echo ""

    if [[ -n "$COMMIT_HASH" ]]; then
        log_info "Rolling back to commit: ${COMMIT_HASH}"

        # Use git to revert in the dashboard directory, then trigger Vercel redeploy
        log_info "Creating revert commit and pushing to trigger Vercel auto-deploy..."
        (
            cd "$ROOT_DIR"
            git checkout "$COMMIT_HASH" -- afrikalytics-dashboard/
            git add afrikalytics-dashboard/
            git commit -m "revert: rollback dashboard to ${COMMIT_HASH}"
            git push origin HEAD
        )

        log_success "Pushed revert commit. Vercel will auto-deploy."
    else
        log_info "No commit hash specified. Using Vercel CLI to rollback to previous deployment..."

        # List recent deployments and rollback
        if [[ -n "${VERCEL_TOKEN:-}" ]]; then
            log_info "Listing recent Vercel deployments..."
            npx vercel ls --token="$VERCEL_TOKEN" 2>/dev/null | head -10

            log_info "Rolling back to previous production deployment..."
            local prev_deployment
            prev_deployment=$(npx vercel ls --token="$VERCEL_TOKEN" 2>/dev/null \
                | grep "Production" | head -2 | tail -1 | awk '{print $2}')

            if [[ -n "$prev_deployment" ]]; then
                npx vercel promote "$prev_deployment" --token="$VERCEL_TOKEN" --yes
                log_success "Promoted previous deployment: ${prev_deployment}"
            else
                log_error "Could not find previous production deployment"
                return 1
            fi
        else
            log_warn "VERCEL_TOKEN not set. Manual rollback required."
            log_info "Options:"
            log_info "  1. Go to https://vercel.com/dashboard and use the UI to rollback"
            log_info "  2. Set VERCEL_TOKEN and re-run this script"
            log_info "  3. Run: ./scripts/rollback.sh dashboard <commit-hash>"
            return 1
        fi
    fi

    # Health check
    if wait_for_health "Dashboard" "${DASHBOARD_URL}" 6 15; then
        log_success "Dashboard rollback completed successfully"
    else
        log_error "Dashboard rollback health check failed"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Rollback API (Railway)
# ---------------------------------------------------------------------------
rollback_api() {
    echo ""
    log_info "=== Rolling back API (Railway) ==="
    echo ""

    if [[ -n "$COMMIT_HASH" ]]; then
        log_info "Rolling back to commit: ${COMMIT_HASH}"

        # Use git to revert the API code and push to trigger Railway auto-deploy
        log_info "Creating revert commit and pushing to trigger Railway auto-deploy..."
        (
            cd "$ROOT_DIR"
            git checkout "$COMMIT_HASH" -- afrikalytics-api/
            git add afrikalytics-api/
            git commit -m "revert: rollback API to ${COMMIT_HASH}"
            git push origin HEAD
        )

        log_success "Pushed revert commit. Railway will auto-deploy."
    else
        log_info "No commit hash specified. Using Railway CLI to rollback..."

        if [[ -n "${RAILWAY_TOKEN:-}" ]]; then
            log_info "Listing recent Railway deployments..."

            # Railway CLI rollback
            RAILWAY_TOKEN="$RAILWAY_TOKEN" npx @railway/cli deployments list 2>/dev/null | head -10

            log_info "Rolling back to previous deployment..."
            local prev_deploy_id
            prev_deploy_id=$(RAILWAY_TOKEN="$RAILWAY_TOKEN" npx @railway/cli deployments list 2>/dev/null \
                | grep -E "SUCCESS|ACTIVE" | head -2 | tail -1 | awk '{print $1}')

            if [[ -n "$prev_deploy_id" ]]; then
                RAILWAY_TOKEN="$RAILWAY_TOKEN" npx @railway/cli rollback "$prev_deploy_id" 2>/dev/null
                log_success "Rolled back to deployment: ${prev_deploy_id}"
            else
                log_error "Could not find previous successful deployment"
                return 1
            fi
        else
            log_warn "RAILWAY_TOKEN not set. Manual rollback required."
            log_info "Options:"
            log_info "  1. Go to https://railway.app/dashboard and redeploy a previous build"
            log_info "  2. Set RAILWAY_TOKEN and re-run this script"
            log_info "  3. Run: ./scripts/rollback.sh api <commit-hash>"
            return 1
        fi
    fi

    # Health check
    if wait_for_health "API" "${API_URL}/health" 12 10; then
        log_success "API rollback completed successfully"
    else
        log_error "API rollback health check failed"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
echo ""
echo -e "${RED}=======================================${NC}"
echo -e "${RED}  Afrikalytics ROLLBACK${NC}"
echo -e "${RED}=======================================${NC}"
echo ""
echo -e "${BOLD}Target:${NC}  ${TARGET}"
echo -e "${BOLD}Commit:${NC}  ${COMMIT_HASH:-latest previous deployment}"
echo ""

preflight

ROLLBACK_FAILURES=0

case "$TARGET" in
    dashboard)
        rollback_dashboard || ((ROLLBACK_FAILURES++))
        ;;
    api)
        rollback_api || ((ROLLBACK_FAILURES++))
        ;;
    all)
        rollback_api || ((ROLLBACK_FAILURES++))
        rollback_dashboard || ((ROLLBACK_FAILURES++))
        ;;
    *)
        log_error "Unknown target: ${TARGET}"
        echo "Usage: $0 [dashboard|api|all] [commit-hash]"
        exit 2
        ;;
esac

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo -e "${CYAN}=======================================${NC}"
echo -e "${CYAN}  Rollback Summary${NC}"
echo -e "${CYAN}=======================================${NC}"
echo ""

if [[ "$ROLLBACK_FAILURES" -eq 0 ]]; then
    echo -e "${GREEN}Rollback completed successfully.${NC}"
    exit 0
else
    echo -e "${RED}Rollback completed with ${ROLLBACK_FAILURES} failure(s).${NC}"
    echo -e "${RED}Manual intervention may be required.${NC}"
    exit 1
fi
