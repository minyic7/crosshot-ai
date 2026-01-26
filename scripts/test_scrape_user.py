import asyncio
import json
import sys
sys.path.insert(0, '.')
from apps.crawler.xhs.scraper import XhsCrawler


async def main():
    crawler = XhsCrawler()

    # 测试获取用户信息
    user_id = "591e353d5e87e752b511b85d"  # Miana是小杨
    print(f"获取用户信息: {user_id}")

    # 测试1: 不加载全部笔记
    print("\n=== 测试1: 初始笔记 (load_all_notes=False) ===")
    user_info = await crawler.scrape_user(user_id, load_all_notes=False)
    print(f"昵称: {user_info.nickname}")
    print(f"小红书号: {user_info.red_id}")
    print(f"性别: {['未知', '男', '女'][user_info.gender]}")
    print(f"IP归属地: {user_info.ip_location}")
    print(f"简介: {user_info.desc[:50]}..." if len(user_info.desc) > 50 else f"简介: {user_info.desc}")
    print(f"关注: {user_info.follows}")
    print(f"粉丝: {user_info.fans}")
    print(f"获赞与收藏: {user_info.interaction}")
    print(f"笔记数: {len(user_info.notes)}")

    if user_info.notes:
        print("\n笔记列表:")
        for i, note in enumerate(user_info.notes[:5], 1):
            print(f"  {i}. [{note.type}] {note.title[:30]}... (赞: {note.likes})")

    # 测试2: 加载更多笔记
    print("\n=== 测试2: 加载更多笔记 (load_all_notes=True, max_scroll=10) ===")
    user_info2 = await crawler.scrape_user(user_id, load_all_notes=True, max_scroll=10)
    print(f"笔记数: {len(user_info2.notes)}")

    if len(user_info2.notes) > len(user_info.notes):
        print(f"新增笔记: {len(user_info2.notes) - len(user_info.notes)} 条")

    # 显示最后几条笔记
    if len(user_info2.notes) > 5:
        print("\n最后5条笔记:")
        for note in user_info2.notes[-5:]:
            print(f"  [{note.type}] {note.title[:30]}... (赞: {note.likes})")


if __name__ == "__main__":
    asyncio.run(main())
