#!/usr/bin/env bash
###############################################################################
# health-check.sh — Afrikalytics health check for API and Dashboard
#
# Usage:
#   ./scripts/health-check.sh [api|dashboard|all]
#
# Environment variables:
#   API_URL         — API base URL (default: https://web-production-ef657.up.railway.app)
#   DASHBOARD_URL   — Dashboard base URL (default: https://afrikalytics.vercel.app)
#   HEALTH_TIMEOUT  — curl timeout in seconds (default: 10)
#
# Exit codes: 0 = all checks passed, 1 = at least one check failed
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
NC='\033[0m' # No Color

log_info()    { echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} ${CYAN}INFO${NC}  $*"; }
log_success() { echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} ${GREEN}OK${NC}    $*"; }
log_warn()    { echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} ${YELLOW}WARN${NC}  $*"; }
log_error()   { echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} ${RED}FAIL${NC}  $*"; }

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_URL="${API_URL:-https://web-production-ef657.up.railway.app}"
DASHBOARD_URL="${DASHBOARD_URL:-https://afrikalytics.vercel.app}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-10}"
TARGET="${1:-all}"

FAILURES=0

# ---------------------------------------------------------------------------
# Helper: check a single endpoint
# ---------------------------------------------------------------------------
check_endpoint() {
    local name="$1"
    local url="$2"
    local expected_status="${3:-200}"

    log_info "Checking ${name} -> ${url}"

    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$HEALTH_TIMEOUT" "$url" 2>/dev/null) || true

    if [[ "$http_code" == "$expected_status" ]]; then
        log_success "${name} returned HTTP ${http_code}"
        return 0
    elif [[ "$http_code" == "000" ]]; then
        log_error "${name} is unreachable (timeout or DNS failure)"
        return 1
    else
        log_error "${name} returned HTTP ${http_code} (expected ${expected_status})"
        return 1
    fi
}

# ---------------------------------------------------------------------------
# API health checks
# ---------------------------------------------------------------------------
check_api() {
    log_info "=== API Health Checks (${API_URL}) ==="
    echo ""

    if ! check_endpoint "API /health" "${API_URL}/health"; then
        ((FAILURES++))
    fi

    if ! check_endpoint "API /docs (Swagger)" "${API_URL}/docs"; then
        ((FAILURES++))
    fi

    if ! check_endpoint "API root /" "${API_URL}/"; then
        ((FAILURES++))
    fi

    # /api/auth/login expects POST, so a GET should return 405 Method Not Allowed
    if ! check_endpoint "API /api/auth/login (method check)" "${API_URL}/api/auth/login" "405"; then
        ((FAILURES++))
    fi

    echo ""
}

# ---------------------------------------------------------------------------
# Dashboard health checks
# ---------------------------------------------------------------------------
check_dashboard() {
    log_info "=== Dashboard Health Checks (${DASHBOARD_URL}) ==="
    echo ""

    if ! check_endpoint "Dashboard /" "${DASHBOARD_URL}/"; then
        ((FAILURES++))
    fi

    if ! check_endpoint "Dashboard /login" "${DASHBOARD_URL}/login"; then
        ((FAILURES++))
    fi

    echo ""
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
echo ""
echo -e "${CYAN}=======================================${NC}"
echo -e "${CYAN}  Afrikalytics Health Check${NC}"
echo -e "${CYAN}=======================================${NC}"
echo ""

case "$TARGET" in
    api)
        check_api
        ;;
    dashboard)
        check_dashboard
        ;;
    all)
        check_api
        check_dashboard
        ;;
    *)
        log_error "Unknown target: ${TARGET}"
        echo "Usage: $0 [api|dashboard|all]"
        exit 2
        ;;
esac

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
if [[ "$FAILURES" -eq 0 ]]; then
    echo -e "${GREEN}All health checks passed.${NC}"
    exit 0
else
    echo -e "${RED}${FAILURES} health check(s) failed.${NC}"
    exit 1
fi
