"""Example app entry point with graceful shutdown."""

import asyncio
import logging
import signal
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

# 全局停止标志
shutdown_event = asyncio.Event()


def handle_shutdown(signum, frame):
    """处理优雅停止信号."""
    sig_name = signal.Signals(signum).name
    logger.info(f"⏸️  收到 {sig_name} 信号，准备优雅停止...")
    shutdown_event.set()


async def main():
    """Main entry point for example app."""
    # 注册信号处理器
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    logger.info("🚀 Example app starting...")

    try:
        while not shutdown_event.is_set():
            # TODO: 实现你的业务逻辑
            logger.info("⚙️  Running...")
            await asyncio.sleep(5)

            if shutdown_event.is_set():
                logger.info("🛑 收到停止信号")
                break

    except KeyboardInterrupt:
        logger.info("⌨️  键盘中断")
    finally:
        logger.info("👋 Example app stopped gracefully")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
