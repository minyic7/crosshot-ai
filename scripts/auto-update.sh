#!/bin/bash
# ============================================
# 自动更新脚本 - 替代 Watchtower
# ============================================
#
# 使用方法：
#   1. 手动运行: ./scripts/auto-update.sh x
#   2. crontab: */5 * * * * /path/to/auto-update.sh x
#
# ============================================

set -e

PLATFORM=${1:-all}
LOG_FILE="/var/log/crosshot-auto-update.log"

# 颜色输出
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

# 获取平台文件
get_compose_files() {
    case $1 in
        x)
            echo "-f docker-compose.yml -f docker-compose.x.yml"
            ;;
        xhs)
            echo "-f docker-compose.yml -f docker-compose.xhs.yml"
            ;;
        all)
            echo "-f docker-compose.yml -f docker-compose.x.yml -f docker-compose.xhs.yml"
            ;;
        *)
            echo "Unknown platform: $1"
            exit 1
            ;;
    esac
}

FILES=$(get_compose_files "$PLATFORM")

log "🔍 检查 $PLATFORM 平台的新镜像..."

# 拉取最新镜像
if docker compose $FILES pull 2>&1 | grep -q "Downloaded newer image"; then
    log "✅ 发现新镜像！开始更新..."

    # 优雅停止并重启
    docker compose $FILES up -d

    log "🎉 更新完成！"

    # 清理旧镜像
    docker image prune -f

    log "🧹 清理完成"
else
    log "ℹ️  已是最新版本，无需更新"
fi
