"""Seed database with realistic test data for UI development."""

import json
import random
from datetime import datetime, timedelta

from apps.database.models import (
    AgentConfig,
    Base,
    Comment,
    Content,
    ContentHistory,
    Database,
    ImageDownloadLog,
    ScrapeLog,
    SearchTask,
    SearchTaskContent,
    User,
)

# Config
DB_PATH = "data/xhs.db"
PLATFORMS = ["x", "xhs"]
CONTENT_TYPES = ["normal", "video"]
SEARCH_STATUSES = ["pending", "running", "completed", "failed"]
KEYWORDS_X = ["2026穿搭女", "#Clawbot", "AI时尚", "春季穿搭趋势", "街拍2026"]
KEYWORDS_XHS = ["春季穿搭", "小个子穿搭", "通勤穿搭", "约会穿搭", "显瘦穿搭"]

NICKNAMES_X = [
    "fashionista_ai", "style_guru_26", "trend_watcher", "outfit_daily",
    "closet_curator", "ootd_lover", "chic_minimal", "retro_vibes",
    "urban_style", "pastel_dream", "denim_queen", "silk_road_style",
    "boho_chic", "neon_nights", "vintage_finds", "layered_look",
    "capsule_wardrobe", "eco_fashion", "runway_recap", "street_snap",
    "color_block", "mono_chrome", "pattern_mix", "oversized_fit",
    "tailored_sharp",
]

NICKNAMES_XHS = [
    "小鹿穿搭日记", "温柔穿搭铺", "每日穿搭灵感", "甜系穿搭师",
    "通勤穿搭指南", "日系穿搭控", "韩系穿搭分享", "法式穿搭笔记",
    "简约穿搭家", "小个子穿搭术", "高级感穿搭", "氛围感穿搭",
    "学生党穿搭", "微胖穿搭", "梨形穿搭", "苹果型穿搭",
    "职场穿搭", "约会穿搭师", "旅行穿搭", "婚礼穿搭",
    "闺蜜穿搭", "情侣穿搭", "亲子穿搭", "复古穿搭铺",
    "极简穿搭家",
]

TITLES = [
    "春季必备单品推荐", "这件外套绝了", "通勤穿搭一周不重样",
    "小个子显高穿搭技巧", "2026年春夏流行色", "极简风穿搭公式",
    "约会穿搭合集", "面试穿搭指南", "旅行穿搭清单",
    "梨形身材穿搭避雷", "微胖女孩的春天", "法式慵懒风穿搭",
    "日系文艺穿搭", "韩系辣妹风", "美式复古穿搭",
    "今日OOTD分享", "开箱 | 春季购物分享", "穿搭灵感来了",
    "这条裙子太美了吧", "被问爆的一套穿搭",
]

COMMENT_TEXTS = [
    "好好看！求链接", "这个颜色好温柔", "已收藏！", "太好看了吧",
    "求同款！", "这件衣服在哪买的", "适合什么身高体重呀",
    "看起来好舒服", "颜色好正", "质量怎么样", "穿着显瘦吗",
    "价格多少呀", "能不能出个视频版", "好种草", "已下单！",
    "Beautiful!", "Love this outfit", "Where to buy?", "So chic!",
    "Great style inspo", "Need this in my life", "Perfect for spring",
]


def rand_time(days_back: int = 30) -> datetime:
    return datetime.utcnow() - timedelta(
        days=random.randint(0, days_back),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )


def rand_count() -> tuple[int, str]:
    n = random.choice([
        random.randint(0, 50),
        random.randint(50, 500),
        random.randint(500, 5000),
        random.randint(5000, 50000),
    ])
    if n >= 10000:
        display = f"{n / 10000:.1f}万"
    else:
        display = str(n)
    return n, display


def seed():
    db = Database(DB_PATH)
    db.init_db()
    session = db.get_session()

    # Check if already seeded
    existing = session.query(User).count()
    if existing > 0:
        print(f"Database already has {existing} users. Clearing and re-seeding...")
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()

    # --- Users ---
    users = []
    for i in range(50):
        platform = PLATFORMS[i % 2]
        nicks = NICKNAMES_X if platform == "x" else NICKNAMES_XHS
        nickname = nicks[i % len(nicks)]
        fans_n, fans_d = rand_count()
        follows_n, follows_d = rand_count()
        inter_n, inter_d = rand_count()

        user = User(
            platform=platform,
            platform_user_id=f"user_{platform}_{i:04d}",
            nickname=f"{nickname}_{i}",
            description=f"Fashion content creator on {platform.upper()}",
            gender=random.choice([0, 1, 2]),
            ip_location=random.choice(["北京", "上海", "广州", "深圳", "杭州", "成都", "New York", "Tokyo"]),
            fans_count_num=fans_n,
            fans_count_display=fans_d,
            follows_count_num=follows_n,
            follows_count_display=follows_d,
            interaction_count_num=inter_n,
            interaction_count_display=inter_d,
            created_at=rand_time(30),
            updated_at=rand_time(7),
        )
        session.add(user)
        users.append(user)

    session.flush()
    print(f"Created {len(users)} users")

    # --- Contents ---
    contents = []
    for i in range(200):
        platform = random.choice(PLATFORMS)
        author = random.choice([u for u in users if u.platform == platform])
        likes_n, likes_d = rand_count()
        collects_n, collects_d = rand_count()
        comments_n, comments_d = rand_count()
        ct = rand_time(30)

        content = Content(
            platform=platform,
            platform_content_id=f"content_{platform}_{i:04d}",
            author_platform=author.platform,
            author_platform_user_id=author.platform_user_id,
            title=random.choice(TITLES),
            content_text=f"这是一条关于穿搭的帖子内容 #{i}，分享今日穿搭灵感。",
            content_type=random.choice(CONTENT_TYPES),
            likes_count_num=likes_n,
            likes_count_display=likes_d,
            collects_count_num=collects_n,
            collects_count_display=collects_d,
            comments_count_num=comments_n,
            comments_count_display=comments_d,
            content_url=f"https://{platform}.com/post/{i:04d}",
            cover_url=f"https://picsum.photos/seed/{platform}_{i}/640/{random.choice([400, 480, 560, 640, 720])}",
            publish_time=ct - timedelta(hours=random.randint(0, 48)),
            created_at=ct,
            updated_at=ct + timedelta(hours=random.randint(0, 24)),
        )
        session.add(content)
        contents.append(content)

    session.flush()
    print(f"Created {len(contents)} contents")

    # --- Comments ---
    comment_count = 0
    for i in range(500):
        content = random.choice(contents)
        author = random.choice([u for u in users if u.platform == content.platform])
        likes_n, likes_d = rand_count()

        comment = Comment(
            platform=content.platform,
            platform_comment_id=f"comment_{content.platform}_{i:04d}",
            content_platform=content.platform,
            platform_content_id=content.platform_content_id,
            user_platform=author.platform,
            platform_user_id=author.platform_user_id,
            comment_text=random.choice(COMMENT_TEXTS),
            likes_count_num=likes_n,
            likes_count_display=likes_d,
            ip_location=random.choice(["北京", "上海", "广州", "深圳", "杭州"]),
            created_at=rand_time(25),
        )
        session.add(comment)
        comment_count += 1

    session.flush()
    print(f"Created {comment_count} comments")

    # --- Content History ---
    history_count = 0
    for content in random.sample(contents, min(80, len(contents))):
        for v in range(random.randint(1, 3)):
            history = ContentHistory(
                platform=content.platform,
                platform_content_id=content.platform_content_id,
                version=v + 1,
                data_json=json.dumps({
                    "likes": content.likes_count_num + random.randint(0, 100) * v,
                    "collects": content.collects_count_num + random.randint(0, 50) * v,
                }),
                change_type=random.choice(["initial", "stats_change", "content_change"]),
                scraped_at=rand_time(20),
            )
            session.add(history)
            history_count += 1

    session.flush()
    print(f"Created {history_count} content history entries")

    # --- Search Tasks ---
    tasks = []
    for i in range(30):
        platform = random.choice(PLATFORMS)
        keywords = KEYWORDS_X if platform == "x" else KEYWORDS_XHS
        status = random.choices(SEARCH_STATUSES, weights=[10, 15, 60, 15])[0]
        ct = rand_time(20)

        task = SearchTask(
            keyword=random.choice(keywords),
            platform=platform,
            status=status,
            contents_found=random.randint(0, 50) if status in ("completed", "running") else 0,
            comments_scraped=random.randint(0, 200) if status == "completed" else 0,
            users_discovered=random.randint(0, 30) if status in ("completed", "running") else 0,
            error_message="Timeout after 30s" if status == "failed" else None,
            created_at=ct,
            started_at=ct + timedelta(minutes=1) if status != "pending" else None,
            completed_at=ct + timedelta(minutes=random.randint(2, 15)) if status in ("completed", "failed") else None,
        )
        session.add(task)
        tasks.append(task)

    session.flush()
    print(f"Created {len(tasks)} search tasks")

    # --- Search Task Contents ---
    stc_count = 0
    for task in [t for t in tasks if t.status in ("completed", "running")]:
        platform_contents = [c for c in contents if c.platform == task.platform]
        sample_size = min(random.randint(3, 10), len(platform_contents))
        for rank, content in enumerate(random.sample(platform_contents, sample_size)):
            stc = SearchTaskContent(
                search_task_id=task.id,
                platform=content.platform,
                platform_content_id=content.platform_content_id,
                rank_position=rank + 1,
                created_at=task.created_at,
            )
            session.add(stc)
            stc_count += 1

    session.flush()
    print(f"Created {stc_count} search task contents")

    # --- Scrape Logs ---
    for i in range(100):
        platform = random.choice(PLATFORMS)
        task_type = random.choice(["search", "comments", "user"])
        status = random.choices(["success", "failed"], weights=[88, 12])[0]

        log = ScrapeLog(
            task_type=task_type,
            target_id=random.choice(KEYWORDS_X if platform == "x" else KEYWORDS_XHS),
            platform=platform,
            status=status,
            items_count=random.randint(1, 30) if status == "success" else 0,
            duration_ms=random.randint(800, 15000),
            error_message="Connection timeout" if status == "failed" else None,
            created_at=rand_time(15),
        )
        session.add(log)

    session.flush()
    print("Created 100 scrape logs")

    # --- Image Download Logs ---
    for i in range(80):
        platform = random.choice(PLATFORMS)
        status = random.choices(["success", "failed", "pending"], weights=[70, 15, 15])[0]

        dl = ImageDownloadLog(
            url=f"https://cdn.{platform}.com/images/{i:04d}.jpg",
            target_type=random.choice(["avatar", "cover", "content_media"]),
            target_id=f"target_{i:04d}",
            platform=platform,
            status=status,
            local_path=f"data/images/{platform}/{i:04d}.jpg" if status == "success" else None,
            attempts=random.randint(1, 3),
            created_at=rand_time(10),
            completed_at=rand_time(9) if status != "pending" else None,
        )
        session.add(dl)

    session.commit()
    print("Created 80 image download logs")

    # --- Agent Configs ---
    seed_agent_configs(session)

    print("\nSeed complete!")
    session.close()


def seed_agent_configs(session):
    """Seed initial agent configuration templates matching docker-compose services."""
    configs = [
        AgentConfig(
            name="human-simulation-xhs",
            display_name="XHS Human Simulation Crawler",
            agent_type="human-simulation",
            platform="xhs",
            description="Simulates human browsing on Xiaohongshu to discover and scrape content organically",
            command='uv run python -m apps.jobs.xhs.human_simulation_job --duration 10080 --keywords "正常穿搭海边"',
            environment_json='{"SIMULATION_DURATION": "10080", "SIMULATION_KEYWORDS": "正常穿搭海边"}',
            cpu_limit="2.0",
            memory_limit="2G",
            cpu_reservation="0.5",
            memory_reservation="1G",
        ),
        AgentConfig(
            name="human-simulation-x",
            display_name="X/Twitter Human Simulation Crawler",
            agent_type="human-simulation",
            platform="x",
            description="Simulates human browsing on X/Twitter to discover and scrape content from the Following timeline",
            command="uv run python -m apps.jobs.x.human_simulation_job --duration 10080",
            environment_json='{"CRAWLER_HEADLESS": "true", "X_SIMULATION_DURATION": "10080"}',
            cpu_limit="2.0",
            memory_limit="2G",
            cpu_reservation="0.5",
            memory_reservation="1G",
        ),
        AgentConfig(
            name="yizhi-x-crawler",
            display_name="X/Twitter AI Crawler (Yizhi)",
            agent_type="yizhi-crawler",
            platform="x",
            description="CrewAI-powered intelligent crawler for X/Twitter with automated keyword analysis",
            command="uv run python -m apps.yizhi.runner",
            environment_json='{"CRAWLER_HEADLESS": "true", "YIZHI_PLATFORM": "x", "YIZHI_KEYWORD": "2026年穿搭女", "YIZHI_MAX_RESULTS": "20"}',
            cpu_limit="2.0",
            memory_limit="2G",
        ),
        AgentConfig(
            name="yizhi-xhs-crawler",
            display_name="XHS AI Crawler (Yizhi)",
            agent_type="yizhi-crawler",
            platform="xhs",
            description="CrewAI-powered intelligent crawler for Xiaohongshu with automated keyword analysis",
            command="uv run python -m apps.yizhi.runner",
            environment_json='{"CRAWLER_HEADLESS": "true", "YIZHI_PLATFORM": "xhs", "YIZHI_KEYWORD": "2026年穿搭女", "YIZHI_MAX_RESULTS": "20"}',
            cpu_limit="2.0",
            memory_limit="2G",
        ),
    ]

    for config in configs:
        existing = session.query(AgentConfig).filter_by(name=config.name).first()
        if not existing:
            session.add(config)

    session.commit()
    print(f"Created/verified {len(configs)} agent configs")


if __name__ == "__main__":
    seed()
