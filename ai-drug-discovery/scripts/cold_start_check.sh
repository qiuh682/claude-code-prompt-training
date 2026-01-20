#!/bin/bash
# =============================================================================
# Cold Start Check - Docker Compose Reliability Test
# 冷启动检查 - Docker Compose 可靠性测试
# =============================================================================
#
# This script verifies that the entire stack starts correctly from scratch.
# 此脚本验证整个技术栈是否能从头正确启动。
#
# Usage: ./scripts/cold_start_check.sh
# Exit codes: 0 = success, 1 = failure
#
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

HEALTH_URL="http://localhost:8000/health"
TIMEOUT_SECONDS=120
POLL_INTERVAL=2

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

log_info() {
    echo "[INFO] $(date '+%H:%M:%S') $1"
}

log_error() {
    echo "[ERROR] $(date '+%H:%M:%S') $1" >&2
}

log_success() {
    echo "[OK] $(date '+%H:%M:%S') $1"
}

# Print diagnostic logs on failure
print_failure_diagnostics() {
    log_error "=== FAILURE DIAGNOSTICS ==="

    echo ""
    log_error "--- Container Status ---"
    docker compose ps || true

    echo ""
    log_error "--- API Logs (last 100 lines) ---"
    docker compose logs --tail=100 api 2>&1 || true

    echo ""
    log_error "--- Postgres Logs (last 100 lines) ---"
    docker compose logs --tail=100 postgres 2>&1 || true

    echo ""
    log_error "--- Redis Logs (last 100 lines) ---"
    docker compose logs --tail=100 redis 2>&1 || true

    echo ""
    log_error "=== END DIAGNOSTICS ==="
}

# Cleanup function - always runs at exit
cleanup() {
    log_info "Cleaning up: docker compose down -v"
    docker compose down -v 2>/dev/null || true
}

# -----------------------------------------------------------------------------
# Main Script
# -----------------------------------------------------------------------------

main() {
    local start_time
    local elapsed
    local http_code

    # Register cleanup trap (runs on exit, error, or interrupt)
    trap cleanup EXIT

    log_info "Starting cold start check..."

    # Step 1: Tear down any existing containers and volumes
    log_info "Step 1/3: Tearing down existing containers..."
    docker compose down -v 2>/dev/null || true

    # Step 2: Build and start fresh
    log_info "Step 2/3: Building and starting containers..."
    if ! docker compose up -d --build; then
        log_error "docker compose up failed!"
        print_failure_diagnostics
        return 1
    fi

    # Step 3: Wait for health endpoint
    log_info "Step 3/3: Waiting for $HEALTH_URL (timeout: ${TIMEOUT_SECONDS}s)..."

    start_time=$(date +%s)

    while true; do
        # Calculate elapsed time
        elapsed=$(( $(date +%s) - start_time ))

        # Check timeout
        if [ "$elapsed" -ge "$TIMEOUT_SECONDS" ]; then
            log_error "Timeout after ${TIMEOUT_SECONDS}s waiting for health endpoint"
            print_failure_diagnostics
            return 1
        fi

        # Try to hit health endpoint
        http_code=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" 2>/dev/null || echo "000")

        if [ "$http_code" = "200" ]; then
            log_success "Health endpoint returned 200 after ${elapsed}s"
            break
        fi

        # Show progress every 10 seconds
        if [ $((elapsed % 10)) -eq 0 ] && [ "$elapsed" -gt 0 ]; then
            log_info "Still waiting... (${elapsed}s elapsed, last HTTP code: $http_code)"
        fi

        sleep "$POLL_INTERVAL"
    done

    # Verify response content
    log_info "Verifying health response content..."
    local response
    response=$(curl -s "$HEALTH_URL")

    if echo "$response" | grep -q '"status"'; then
        log_success "Health response valid: $response"
    else
        log_error "Health response invalid: $response"
        print_failure_diagnostics
        return 1
    fi

    echo ""
    log_success "=== COLD START CHECK PASSED ==="
    echo ""

    return 0
}

# Run main function
main "$@"
