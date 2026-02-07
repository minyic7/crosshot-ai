#!/bin/bash
# ============================================
# Docker Compose 帮助脚本
# ============================================
#
# 简化多文件 docker-compose 命令
#
# ============================================

set -e

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 基础文件
BASE_FILE="docker-compose.yml"

# 显示帮助
function show_help() {
    echo -e "${BLUE}Docker Compose 帮助脚本${NC}"
    echo ""
    echo "用法："
    echo "  ./scripts/compose-helper.sh <command> <platform>"
    echo ""
    echo "命令："
    echo "  up <platform>       启动指定平台"
    echo "  down <platform>     停止指定平台"
    echo "  logs <platform>     查看平台日志"
    echo "  restart <platform>  重启平台"
    echo "  ps <platform>       查看平台容器状态"
    echo "  all                 管理所有平台"
    echo ""
    echo "平台："
    echo "  x, xhs, watchtower, all"
    echo ""
    echo "示例："
    echo "  ./scripts/compose-helper.sh up x          # 启动 X 平台"
    echo "  ./scripts/compose-helper.sh logs xhs      # 查看小红书日志"
    echo "  ./scripts/compose-helper.sh down all      # 停止所有平台"
    echo ""
}

# 获取平台文件
function get_platform_files() {
    local platform=$1
    case $platform in
        x)
            echo "-f $BASE_FILE -f docker-compose.x.yml"
            ;;
        xhs)
            echo "-f $BASE_FILE -f docker-compose.xhs.yml"
            ;;
        watchtower)
            echo "-f $BASE_FILE -f docker-compose.watchtower.yml"
            ;;
        all)
            echo "-f $BASE_FILE -f docker-compose.x.yml -f docker-compose.xhs.yml"
            ;;
        *)
            echo "未知平台: $platform"
            exit 1
            ;;
    esac
}

# 执行命令
function run_command() {
    local cmd=$1
    local platform=$2

    if [ -z "$platform" ]; then
        echo -e "${YELLOW}错误: 请指定平台${NC}"
        show_help
        exit 1
    fi

    local files=$(get_platform_files $platform)

    echo -e "${GREEN}执行: docker-compose $files $cmd${NC}"
    docker-compose $files $cmd "${@:3}"
}

# 主逻辑
case $1 in
    up)
        run_command "up -d" $2
        echo -e "${GREEN}✅ $2 平台已启动${NC}"
        ;;
    down)
        run_command "down" $2
        echo -e "${GREEN}✅ $2 平台已停止${NC}"
        ;;
    logs)
        run_command "logs -f --tail=100" $2 "${@:3}"
        ;;
    restart)
        run_command "restart" $2
        echo -e "${GREEN}✅ $2 平台已重启${NC}"
        ;;
    ps)
        run_command "ps" $2
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${YELLOW}未知命令: $1${NC}"
        show_help
        exit 1
        ;;
esac
