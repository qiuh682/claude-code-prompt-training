#!/bin/bash
# =============================================================================
# Docker Compose Smoke Test Script
# Docker Compose 冒烟测试脚本
# =============================================================================
#
# This script validates that the entire stack (FastAPI + Postgres + Redis)
# boots correctly and passes health checks.
# 此脚本验证整个技术栈（FastAPI + Postgres + Redis）能正确启动并通过健康检查。
#
# Usage / 用法:
#   ./scripts/smoke_compose.sh
#   ./scripts/smoke_compose.sh --keep    # Don't clean up on success
#   ./scripts/smoke_compose.sh --verbose # Show detailed output
#
# Exit codes / 退出码:
#   0 - All checks passed / 所有检查通过
#   1 - Health check failed / 健康检查失败
#   2 - Container startup failed / 容器启动失败
#   3 - Timeout waiting for services / 等待服务超时
#
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration / 配置
# -----------------------------------------------------------------------------
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
readonly COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"

# Timeouts and retries / 超时和重试配置
readonly HEALTH_TIMEOUT=120        # Max seconds to wait for health / 等待健康的最大秒数
readonly HEALTH_INTERVAL=2         # Seconds between health checks / 健康检查间隔秒数
readonly STARTUP_WAIT=5            # Seconds to wait after compose up / compose up 后等待秒数

# Endpoints / 端点
readonly API_HOST="${API_HOST:-localhost}"
readonly API_PORT="${API_PORT:-8000}"
readonly HEALTH_ENDPOINT="http://${API_HOST}:${API_PORT}/health"
readonly READY_ENDPOINT="http://${API_HOST}:${API_PORT}/health/ready"

# Colors for output / 输出颜色
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color / 无颜色

# Flags / 标志
KEEP_RUNNING=false
VERBOSE=false

# -----------------------------------------------------------------------------
# Helper Functions / 辅助函数
# -----------------------------------------------------------------------------

log_info() {
    # Print info message / 打印信息消息
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    # Print success message / 打印成功消息
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_warning() {
    # Print warning message / 打印警告消息
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    # Print error message / 打印错误消息
    echo -e "${RED}[FAIL]${NC} $1"
}

log_step() {
    # Print step header / 打印步骤标题
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_banner() {
    # Print script banner / 打印脚本横幅
    echo ""
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║     Docker Compose Smoke Test / Docker Compose 冒烟测试      ║${NC}"
    echo -e "${BLUE}║         FastAPI + PostgreSQL + Redis Stack                   ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

show_container_status() {
    # Show status of all containers / 显示所有容器的状态
    log_step "Container Status / 容器状态"
    docker compose -f "$COMPOSE_FILE" ps -a
}

show_container_logs() {
    # Show last N lines of logs for all services / 显示所有服务的最后 N 行日志
    local lines="${1:-50}"
    log_step "Container Logs (last ${lines} lines) / 容器日志（最后 ${lines} 行）"

    echo ""
    echo -e "${YELLOW}=== PostgreSQL Logs / PostgreSQL 日志 ===${NC}"
    docker compose -f "$COMPOSE_FILE" logs --tail="$lines" postgres 2>/dev/null || echo "No logs available"

    echo ""
    echo -e "${YELLOW}=== Redis Logs / Redis 日志 ===${NC}"
    docker compose -f "$COMPOSE_FILE" logs --tail="$lines" redis 2>/dev/null || echo "No logs available"

    echo ""
    echo -e "${YELLOW}=== API Logs / API 日志 ===${NC}"
    docker compose -f "$COMPOSE_FILE" logs --tail="$lines" api 2>/dev/null || echo "No logs available"
}

cleanup() {
    # Cleanup function called on script exit / 脚本退出时调用的清理函数
    local exit_code=$?

    if [[ "$KEEP_RUNNING" == "false" && $exit_code -ne 0 ]]; then
        log_warning "Cleaning up after failure... / 失败后清理中..."
        docker compose -f "$COMPOSE_FILE" down -v 2>/dev/null || true
    fi

    exit $exit_code
}

wait_for_health() {
    # Wait for health endpoint to return 200 / 等待健康端点返回 200
    local endpoint="$1"
    local description="$2"
    local timeout="$3"
    local interval="$4"

    local elapsed=0
    local attempt=1

    log_info "Waiting for $description... / 等待 $description..."
    log_info "Endpoint: $endpoint"
    log_info "Timeout: ${timeout}s, Interval: ${interval}s"

    while [[ $elapsed -lt $timeout ]]; do
        # Try to hit the health endpoint / 尝试访问健康端点
        local http_code
        http_code=$(curl -s -o /dev/null -w "%{http_code}" "$endpoint" 2>/dev/null || echo "000")

        if [[ "$http_code" == "200" ]]; then
            log_success "$description is healthy! (attempt $attempt, ${elapsed}s elapsed)"
            log_success "$description 已健康！（第 $attempt 次尝试，已用 ${elapsed} 秒）"
            return 0
        fi

        if [[ "$VERBOSE" == "true" ]]; then
            log_info "Attempt $attempt: HTTP $http_code (${elapsed}s elapsed)"
        fi

        sleep "$interval"
        elapsed=$((elapsed + interval))
        attempt=$((attempt + 1))
    done

    log_error "$description failed to become healthy after ${timeout}s"
    log_error "$description 在 ${timeout} 秒后仍未健康"
    return 1
}

verify_ready_endpoint() {
    # Verify the ready endpoint returns expected data / 验证就绪端点返回预期数据
    log_info "Verifying ready endpoint... / 验证就绪端点..."

    local response
    response=$(curl -s "$READY_ENDPOINT" 2>/dev/null || echo "{}")

    # Check if response contains expected fields / 检查响应是否包含预期字段
    if echo "$response" | grep -q '"database":"connected"' && \
       echo "$response" | grep -q '"redis":"connected"'; then
        log_success "Ready endpoint verified: $response"
        log_success "就绪端点已验证: $response"
        return 0
    else
        log_error "Ready endpoint returned unexpected response: $response"
        log_error "就绪端点返回意外响应: $response"
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Main Test Steps / 主测试步骤
# -----------------------------------------------------------------------------

step_cleanup() {
    # Step 1: Clean up existing containers and volumes
    # 步骤 1：清理现有容器和卷
    log_step "Step 1/5: Cleanup / 步骤 1/5: 清理"

    log_info "Stopping and removing containers, networks, and volumes..."
    log_info "停止并删除容器、网络和卷..."

    docker compose -f "$COMPOSE_FILE" down -v 2>/dev/null || true

    log_success "Cleanup complete / 清理完成"
}

step_build_and_start() {
    # Step 2: Build and start services
    # 步骤 2：构建并启动服务
    log_step "Step 2/5: Build & Start / 步骤 2/5: 构建并启动"

    log_info "Building and starting services..."
    log_info "构建并启动服务中..."

    if [[ "$VERBOSE" == "true" ]]; then
        docker compose -f "$COMPOSE_FILE" up -d --build
    else
        docker compose -f "$COMPOSE_FILE" up -d --build 2>&1 | tail -20
    fi

    local exit_code=${PIPESTATUS[0]}
    if [[ $exit_code -ne 0 ]]; then
        log_error "Failed to start services (exit code: $exit_code)"
        log_error "启动服务失败（退出码: $exit_code）"
        return 2
    fi

    log_success "Services started / 服务已启动"
    log_info "Waiting ${STARTUP_WAIT}s for initial startup... / 等待 ${STARTUP_WAIT} 秒进行初始启动..."
    sleep "$STARTUP_WAIT"
}

step_check_containers() {
    # Step 3: Verify containers are running
    # 步骤 3：验证容器正在运行
    log_step "Step 3/5: Container Check / 步骤 3/5: 容器检查"

    log_info "Checking container status... / 检查容器状态..."

    local running_count
    running_count=$(docker compose -f "$COMPOSE_FILE" ps --status running -q | wc -l)

    if [[ $running_count -lt 3 ]]; then
        log_error "Expected 3 running containers, found $running_count"
        log_error "预期 3 个运行中的容器，实际找到 $running_count 个"
        show_container_status
        return 2
    fi

    log_success "All 3 containers are running / 所有 3 个容器正在运行"

    if [[ "$VERBOSE" == "true" ]]; then
        show_container_status
    fi
}

step_health_check() {
    # Step 4: Wait for health endpoint
    # 步骤 4：等待健康端点
    log_step "Step 4/5: Health Check / 步骤 4/5: 健康检查"

    if ! wait_for_health "$HEALTH_ENDPOINT" "API Health" "$HEALTH_TIMEOUT" "$HEALTH_INTERVAL"; then
        return 3
    fi
}

step_readiness_check() {
    # Step 5: Verify full readiness
    # 步骤 5：验证完全就绪
    log_step "Step 5/5: Readiness Check / 步骤 5/5: 就绪检查"

    if ! verify_ready_endpoint; then
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Main Function / 主函数
# -----------------------------------------------------------------------------

main() {
    # Parse arguments / 解析参数
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --keep)
                KEEP_RUNNING=true
                shift
                ;;
            --verbose|-v)
                VERBOSE=true
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [--keep] [--verbose]"
                echo "  --keep     Don't clean up containers on success"
                echo "  --verbose  Show detailed output"
                exit 0
                ;;
            *)
                log_error "Unknown argument: $1"
                exit 1
                ;;
        esac
    done

    # Set up cleanup trap / 设置清理陷阱
    trap cleanup EXIT

    # Print banner / 打印横幅
    print_banner

    log_info "Project directory: $PROJECT_DIR"
    log_info "Compose file: $COMPOSE_FILE"
    log_info "Health endpoint: $HEALTH_ENDPOINT"
    echo ""

    # Record start time / 记录开始时间
    local start_time
    start_time=$(date +%s)

    # Run test steps / 运行测试步骤
    local exit_code=0

    step_cleanup || exit_code=$?
    [[ $exit_code -eq 0 ]] && step_build_and_start || exit_code=$?
    [[ $exit_code -eq 0 ]] && step_check_containers || exit_code=$?
    [[ $exit_code -eq 0 ]] && step_health_check || exit_code=$?
    [[ $exit_code -eq 0 ]] && step_readiness_check || exit_code=$?

    # Calculate duration / 计算耗时
    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))

    # Print results / 打印结果
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

    if [[ $exit_code -eq 0 ]]; then
        echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
        echo -e "${GREEN}║          ✓ SMOKE TEST PASSED / 冒烟测试通过 ✓            ║${NC}"
        echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
        log_success "All checks passed in ${duration}s / 所有检查在 ${duration} 秒内通过"

        if [[ "$KEEP_RUNNING" == "true" ]]; then
            log_info "Containers kept running (--keep flag)"
            log_info "容器保持运行中（--keep 标志）"
            show_container_status
        else
            log_info "Cleaning up... / 清理中..."
            docker compose -f "$COMPOSE_FILE" down -v 2>/dev/null || true
        fi
    else
        echo -e "${RED}╔══════════════════════════════════════════════════════════╗${NC}"
        echo -e "${RED}║          ✗ SMOKE TEST FAILED / 冒烟测试失败 ✗            ║${NC}"
        echo -e "${RED}╚══════════════════════════════════════════════════════════╝${NC}"
        log_error "Test failed after ${duration}s with exit code $exit_code"
        log_error "测试在 ${duration} 秒后失败，退出码 $exit_code"

        # Show diagnostic information / 显示诊断信息
        show_container_status
        show_container_logs 50
    fi

    echo ""
    return $exit_code
}

# Run main function / 运行主函数
main "$@"
