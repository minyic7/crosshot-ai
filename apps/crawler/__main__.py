"""Crawler service entry point - 通用爬虫，支持多平台配置."""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

# 配置日志
log_level = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

# 全局停止标志
shutdown_event = asyncio.Event()

# 从环境变量读取配置
PLATFORM = os.getenv("PLATFORM", "unknown")
KEYWORDS = os.getenv("KEYWORDS", "").split(",")
MAX_RESULTS = int(os.getenv("MAX_RESULTS", "100"))
INTERVAL = int(os.getenv("INTERVAL", "3600"))
ENV = os.getenv("ENV", "development")


def handle_shutdown(signum, frame):
    """处理优雅停止信号."""
    sig_name = signal.Signals(signum).name
    logger.info(f"⏸️  [{PLATFORM}] 收到 {sig_name} 信号，准备优雅停止...")
    shutdown_event.set()


async def save_progress(state: dict):
    """保存爬虫进度到磁盘."""
    logger.info(f"💾 [{PLATFORM}] 正在保存进度...")

    # 创建数据目录
    data_dir = Path("/app/data")
    data_dir.mkdir(parents=True, exist_ok=True)

    # 保存到 JSON 文件
    import json
    progress_file = data_dir / f"progress_{PLATFORM}.json"
    progress_file.write_text(json.dumps(state, ensure_ascii=False, indent=2))

    logger.info(f"✅ [{PLATFORM}] 进度已保存到 {progress_file}")


async def load_progress() -> dict:
    """从磁盘加载爬虫进度."""
    logger.info(f"📂 [{PLATFORM}] 加载之前的进度...")

    import json
    progress_file = Path("/app/data") / f"progress_{PLATFORM}.json"

    if progress_file.exists():
        try:
            state = json.loads(progress_file.read_text())
            logger.info(f"✅ [{PLATFORM}] 已加载进度: {state.get('last_update', 'unknown')}")
            return state
        except Exception as e:
            logger.warning(f"⚠️  [{PLATFORM}] 加载进度失败: {e}")
            return {}

    logger.info(f"✅ [{PLATFORM}] 从头开始")
    return {}


async def crawl_platform(platform: str, keywords: list[str]) -> dict:
    """
    根据平台类型爬取数据 (Mock 实现).

    Args:
        platform: 平台名称 (x, xhs, douyin 等)
        keywords: 爬取关键词列表

    Returns:
        爬取结果统计
    """
    logger.info(f"🔍 [{platform}] 开始爬取，关键词: {keywords}")

    import random
    import datetime

    # 模拟不同平台的数据结构
    platform_configs = {
        "x": {
            "name": "X (Twitter)",
            "content_type": "post",
            "avg_engagement": (100, 5000),
            "media_types": ["image", "video", "gif"],
        },
        "xhs": {
            "name": "小红书",
            "content_type": "note",
            "avg_engagement": (500, 10000),
            "media_types": ["image", "video"],
        },
        "douyin": {
            "name": "抖音",
            "content_type": "video",
            "avg_engagement": (1000, 50000),
            "media_types": ["video"],
        },
    }

    config = platform_configs.get(platform, {
        "name": platform,
        "content_type": "content",
        "avg_engagement": (10, 1000),
        "media_types": ["image"],
    })

    logger.info(f"📱 [{platform}] 平台: {config['name']}")

    # 模拟爬取过程
    items_scraped = []
    total_items = random.randint(max(5, MAX_RESULTS - 20), MAX_RESULTS)

    for i in range(total_items):
        # 检查是否需要停止
        if shutdown_event.is_set():
            logger.info(f"⚠️  [{platform}] 爬取过程中收到停止信号，已爬取 {len(items_scraped)} 项")
            break

        # 模拟网络延迟
        await asyncio.sleep(random.uniform(0.1, 0.5))

        # 生成 mock 数据
        keyword = random.choice(keywords) if keywords else "default"
        item = {
            "id": f"{platform}_{i+1}_{random.randint(10000, 99999)}",
            "platform": platform,
            "keyword": keyword,
            "type": config["content_type"],
            "title": f"Mock {config['content_type']} about {keyword} #{i+1}",
            "author": f"user_{random.randint(1000, 9999)}",
            "engagement": {
                "likes": random.randint(*config["avg_engagement"]),
                "comments": random.randint(10, 500),
                "shares": random.randint(5, 200),
            },
            "media": {
                "type": random.choice(config["media_types"]),
                "count": random.randint(1, 9),
            },
            "timestamp": datetime.datetime.now().isoformat(),
        }

        items_scraped.append(item)

        # 每10个打印一次进度
        if (i + 1) % 10 == 0:
            logger.info(f"⏳ [{platform}] 进度: {i+1}/{total_items} ({(i+1)/total_items*100:.1f}%)")

    # 保存 mock 数据到文件
    data_dir = Path("/app/data")
    data_dir.mkdir(parents=True, exist_ok=True)

    import json
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    data_file = data_dir / f"mock_data_{timestamp}.json"

    with open(data_file, 'w', encoding='utf-8') as f:
        json.dump({
            "platform": platform,
            "keywords": keywords,
            "scraped_at": datetime.datetime.now().isoformat(),
            "total_items": len(items_scraped),
            "items": items_scraped,
        }, f, ensure_ascii=False, indent=2)

    logger.info(f"💾 [{platform}] Mock 数据已保存到: {data_file}")
    logger.info(f"✅ [{platform}] 爬取完成: {len(items_scraped)} 个 {config['content_type']}")

    # 统计信息
    total_likes = sum(item["engagement"]["likes"] for item in items_scraped)
    total_comments = sum(item["engagement"]["comments"] for item in items_scraped)
    media_types_count = {}
    for item in items_scraped:
        media_type = item["media"]["type"]
        media_types_count[media_type] = media_types_count.get(media_type, 0) + 1

    # 新功能：计算平均互动率
    avg_likes = total_likes // len(items_scraped) if items_scraped else 0
    avg_comments = total_comments // len(items_scraped) if items_scraped else 0

    logger.info(f"📊 [{platform}] 统计:")
    logger.info(f"   - 总互动: {total_likes:,} 点赞, {total_comments:,} 评论")
    logger.info(f"   - 平均互动: {avg_likes:,} 点赞/条, {avg_comments:,} 评论/条")  # 🆕 新功能
    logger.info(f"   - 媒体类型: {media_types_count}")

    return {
        "platform": platform,
        "platform_name": config["name"],
        "keywords": keywords,
        "items_scraped": len(items_scraped),
        "total_likes": total_likes,
        "total_comments": total_comments,
        "media_types": media_types_count,
        "data_file": str(data_file),
        "timestamp": datetime.datetime.now().isoformat(),
    }


async def crawler_loop():
    """持续运行的爬虫主循环."""
    logger.info(f"🕷️  [{PLATFORM}] 爬虫循环启动...")
    logger.info(f"📋 [{PLATFORM}] 配置:")
    logger.info(f"   - 平台: {PLATFORM}")
    logger.info(f"   - 关键词: {KEYWORDS}")
    logger.info(f"   - 最大结果数: {MAX_RESULTS}")
    logger.info(f"   - 爬取间隔: {INTERVAL}秒")

    # 加载之前的进度
    state = await load_progress()
    iteration = state.get("iteration", 0)

    try:
        while not shutdown_event.is_set():
            iteration += 1
            logger.info(f"🔄 [{PLATFORM}] 第 {iteration} 次爬取...")

            # 执行爬取
            result = await crawl_platform(PLATFORM, KEYWORDS)

            # 更新状态
            import datetime
            state = {
                "platform": PLATFORM,
                "iteration": iteration,
                "last_update": datetime.datetime.now().isoformat(),
                "last_result": result,
            }

            # 定期保存进度（每次爬取后）
            await save_progress(state)

            # 等待下一次爬取
            logger.info(f"⏰ [{PLATFORM}] 等待 {INTERVAL} 秒后继续...")

            # 可中断的等待
            try:
                await asyncio.wait_for(
                    shutdown_event.wait(),
                    timeout=INTERVAL
                )
                # 如果 shutdown_event 被设置，退出循环
                if shutdown_event.is_set():
                    logger.info(f"🛑 [{PLATFORM}] 检测到停止信号")
                    break
            except asyncio.TimeoutError:
                # 等待超时，继续下一次爬取
                continue

    except asyncio.CancelledError:
        logger.info(f"⚠️  [{PLATFORM}] 任务被取消")
        raise
    except Exception as e:
        logger.error(f"❌ [{PLATFORM}] 爬虫错误: {e}", exc_info=True)
        raise
    finally:
        # 无论如何都保存进度
        await save_progress(state)


async def main():
    """Main entry point for crawler service."""
    global KEYWORDS  # 声明使用全局变量

    # 注册信号处理器
    signal.signal(signal.SIGTERM, handle_shutdown)  # Docker stop
    signal.signal(signal.SIGINT, handle_shutdown)   # Ctrl+C

    logger.info(f"🚀 Crawler service starting...")
    logger.info(f"📋 进程 ID: {os.getpid()}")
    logger.info(f"🏷️  平台: {PLATFORM}")
    logger.info(f"🌍 环境: {ENV}")

    # 验证配置
    if PLATFORM == "unknown":
        logger.error("❌ 未设置 PLATFORM 环境变量！")
        logger.error("   请在 docker-compose.yml 中设置 PLATFORM=x 或 PLATFORM=xhs")
        sys.exit(1)

    if not KEYWORDS or KEYWORDS == ['']:
        logger.warning("⚠️  未设置 KEYWORDS，将使用默认关键词")
        KEYWORDS = ["default"]

    try:
        # 运行爬虫循环
        await crawler_loop()

    except KeyboardInterrupt:
        logger.info(f"⌨️  [{PLATFORM}] 收到键盘中断")
    except Exception as e:
        logger.error(f"💥 [{PLATFORM}] 致命错误: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info(f"👋 [{PLATFORM}] Crawler service stopped gracefully")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
