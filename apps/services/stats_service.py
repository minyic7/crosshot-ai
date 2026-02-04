"""Stats service for database aggregate queries."""

from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from apps.database.models import (
    Comment,
    Content,
    ContentHistory,
    Database,
    ImageDownloadLog,
    ScrapeLog,
    SearchTask,
    User,
)


class StatsService:
    def __init__(self, db_path: str = "data/xhs.db"):
        self.db = Database(db_path)

    def get_overview(self) -> dict:
        """Dashboard overview: total counts + today's new."""
        session = self.db.get_session()
        try:
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

            total_contents = session.query(func.count(Content.id)).scalar() or 0
            total_comments = session.query(func.count(Comment.id)).scalar() or 0
            total_users = session.query(func.count(User.id)).scalar() or 0
            total_tasks = session.query(func.count(SearchTask.id)).scalar() or 0

            today_contents = session.query(func.count(Content.id)).filter(
                Content.created_at >= today_start
            ).scalar() or 0
            today_comments = session.query(func.count(Comment.id)).filter(
                Comment.created_at >= today_start
            ).scalar() or 0
            today_users = session.query(func.count(User.id)).filter(
                User.created_at >= today_start
            ).scalar() or 0

            return {
                "total_contents": total_contents,
                "total_comments": total_comments,
                "total_users": total_users,
                "total_tasks": total_tasks,
                "today_contents": today_contents,
                "today_comments": today_comments,
                "today_users": today_users,
            }
        finally:
            session.close()

    def get_table_stats(self) -> list[dict]:
        """Row count + today's growth for each table."""
        session = self.db.get_session()
        try:
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

            tables = [
                ("users", User, User.created_at),
                ("contents", Content, Content.created_at),
                ("comments", Comment, Comment.created_at),
                ("content_history", ContentHistory, ContentHistory.scraped_at),
                ("search_tasks", SearchTask, SearchTask.created_at),
                ("scrape_logs", ScrapeLog, ScrapeLog.created_at),
                ("image_download_logs", ImageDownloadLog, ImageDownloadLog.created_at),
            ]
            result = []
            for name, model, time_col in tables:
                count = session.query(func.count(model.id)).scalar() or 0
                today = session.query(func.count(model.id)).filter(
                    time_col >= today_start
                ).scalar() or 0
                result.append({"table": name, "count": count, "today": today})
            return result
        finally:
            session.close()

    def get_storage_info(self) -> dict:
        """Database file size and data directory stats."""
        db_path = Path(self.db.db_path)
        data_dir = db_path.parent

        # DB file size
        db_size_bytes = db_path.stat().st_size if db_path.exists() else 0

        # Total data directory size (includes downloaded media)
        total_bytes = 0
        file_count = 0
        for f in data_dir.rglob("*"):
            if f.is_file():
                total_bytes += f.stat().st_size
                file_count += 1

        return {
            "db_file_size_bytes": db_size_bytes,
            "db_file_size_mb": round(db_size_bytes / (1024 * 1024), 2),
            "data_dir_size_bytes": total_bytes,
            "data_dir_size_mb": round(total_bytes / (1024 * 1024), 2),
            "data_dir_file_count": file_count,
            "db_path": str(db_path),
        }

    def get_platform_breakdown(self) -> dict:
        """Contents, users, comments grouped by platform."""
        session = self.db.get_session()
        try:
            contents_by_platform = dict(
                session.query(Content.platform, func.count(Content.id))
                .group_by(Content.platform)
                .all()
            )
            users_by_platform = dict(
                session.query(User.platform, func.count(User.id))
                .group_by(User.platform)
                .all()
            )
            comments_by_platform = dict(
                session.query(Comment.platform, func.count(Comment.id))
                .group_by(Comment.platform)
                .all()
            )
            return {
                "contents": contents_by_platform,
                "users": users_by_platform,
                "comments": comments_by_platform,
            }
        finally:
            session.close()

    def get_content_type_breakdown(self) -> dict:
        """Contents grouped by content_type."""
        session = self.db.get_session()
        try:
            rows = (
                session.query(Content.content_type, func.count(Content.id))
                .group_by(Content.content_type)
                .all()
            )
            return {ct or "unknown": count for ct, count in rows}
        finally:
            session.close()

    def get_search_task_summary(self) -> list[dict]:
        """Recent search tasks with status."""
        session = self.db.get_session()
        try:
            tasks = (
                session.query(SearchTask)
                .order_by(SearchTask.created_at.desc())
                .limit(20)
                .all()
            )
            return [
                {
                    "id": t.id,
                    "keyword": t.keyword,
                    "platform": t.platform,
                    "status": t.status,
                    "contents_found": t.contents_found,
                    "comments_scraped": t.comments_scraped,
                    "users_discovered": t.users_discovered,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "started_at": t.started_at.isoformat() if t.started_at else None,
                    "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                    "error_message": t.error_message,
                }
                for t in tasks
            ]
        finally:
            session.close()

    def get_scrape_health(
        self, hours: int | None = None, platform: str | None = None
    ) -> dict:
        """Success/failure rates from scrape_logs with optional filters."""
        session = self.db.get_session()
        try:
            base = session.query(ScrapeLog.id)
            if hours is not None:
                cutoff = datetime.utcnow() - timedelta(hours=hours)
                base = base.filter(ScrapeLog.created_at >= cutoff)
            if platform:
                base = base.filter(ScrapeLog.platform == platform)

            total = base.count()
            success = base.filter(ScrapeLog.status == "success").count()
            failed = base.filter(ScrapeLog.status == "failed").count()

            avg_q = session.query(func.avg(ScrapeLog.duration_ms)).filter(
                ScrapeLog.status == "success"
            )
            if hours is not None:
                cutoff = datetime.utcnow() - timedelta(hours=hours)
                avg_q = avg_q.filter(ScrapeLog.created_at >= cutoff)
            if platform:
                avg_q = avg_q.filter(ScrapeLog.platform == platform)
            avg_duration = avg_q.scalar() or 0

            return {
                "total": total,
                "success": success,
                "failed": failed,
                "success_rate": round(success / total * 100, 1) if total > 0 else 0,
                "avg_duration_ms": round(avg_duration),
            }
        finally:
            session.close()

    def get_recent_activity(self, limit: int = 20) -> list[dict]:
        """Recent scrape_logs as activity feed."""
        session = self.db.get_session()
        try:
            logs = (
                session.query(ScrapeLog)
                .order_by(ScrapeLog.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": log.id,
                    "task_type": log.task_type,
                    "target_id": log.target_id,
                    "platform": log.platform,
                    "status": log.status,
                    "items_count": log.items_count,
                    "duration_ms": log.duration_ms,
                    "error_message": log.error_message,
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                }
                for log in logs
            ]
        finally:
            session.close()

    def get_growth(self, days: int = 7) -> dict:
        """Daily new contents/users/comments over past N days."""
        session = self.db.get_session()
        try:
            result = {"contents": [], "users": [], "comments": []}
            now = datetime.utcnow()

            for i in range(days - 1, -1, -1):
                day_start = (now - timedelta(days=i)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                day_end = day_start + timedelta(days=1)
                date_str = day_start.strftime("%m-%d")

                contents_count = session.query(func.count(Content.id)).filter(
                    Content.created_at >= day_start,
                    Content.created_at < day_end,
                ).scalar() or 0

                users_count = session.query(func.count(User.id)).filter(
                    User.created_at >= day_start,
                    User.created_at < day_end,
                ).scalar() or 0

                comments_count = session.query(func.count(Comment.id)).filter(
                    Comment.created_at >= day_start,
                    Comment.created_at < day_end,
                ).scalar() or 0

                result["contents"].append({"date": date_str, "count": contents_count})
                result["users"].append({"date": date_str, "count": users_count})
                result["comments"].append({"date": date_str, "count": comments_count})

            return result
        finally:
            session.close()

    def get_content_list(
        self,
        page: int = 1,
        limit: int = 20,
        platform: str | None = None,
        sort: str = "newest",
    ) -> dict:
        """Paginated content list with author info for the card wall."""
        session = self.db.get_session()
        try:
            query = session.query(Content).options(joinedload(Content.author))

            if platform:
                query = query.filter(Content.platform == platform)

            if sort == "popular":
                query = query.order_by(Content.likes_count_num.desc())
            else:
                query = query.order_by(Content.created_at.desc())

            total = query.count()
            items = query.offset((page - 1) * limit).limit(limit).all()

            return {
                "items": [
                    {
                        "id": c.id,
                        "title": c.title,
                        "content_text": (c.content_text or "")[:200],
                        "content_type": c.content_type,
                        "cover_url": c.cover_url,
                        "platform": c.platform,
                        "likes": c.likes_count_num or 0,
                        "collects": c.collects_count_num or 0,
                        "comments": c.comments_count_num or 0,
                        "publish_time": c.publish_time.isoformat() if c.publish_time else None,
                        "created_at": c.created_at.isoformat() if c.created_at else None,
                        "author": {
                            "nickname": c.author.nickname if c.author else None,
                            "avatar_url": c.author.avatar_url if c.author else None,
                            "platform": c.author.platform if c.author else c.platform,
                        },
                    }
                    for c in items
                ],
                "total": total,
                "page": page,
                "limit": limit,
                "has_more": (page * limit) < total,
            }
        finally:
            session.close()

    def get_content_detail(self, content_id: int) -> dict | None:
        """Full content detail with author, comments, and images."""
        session = self.db.get_session()
        try:
            c = (
                session.query(Content)
                .options(
                    joinedload(Content.author),
                    joinedload(Content.comments).joinedload(Comment.user),
                )
                .filter(Content.id == content_id)
                .first()
            )
            if not c:
                return None

            comments_list = sorted(
                c.comments, key=lambda x: x.created_at or datetime.min, reverse=True
            )

            return {
                "id": c.id,
                "title": c.title,
                "content_text": c.content_text,
                "content_type": c.content_type,
                "cover_url": c.cover_url,
                "content_url": c.content_url,
                "platform": c.platform,
                "platform_content_id": c.platform_content_id,
                "likes": c.likes_count_num or 0,
                "likes_display": c.likes_count_display or "0",
                "collects": c.collects_count_num or 0,
                "collects_display": c.collects_count_display or "0",
                "comments_count": c.comments_count_num or 0,
                "comments_display": c.comments_count_display or "0",
                "image_urls": c.get_image_urls(),
                "video_urls": c.get_video_urls(),
                "publish_time": c.publish_time.isoformat() if c.publish_time else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "author": {
                    "nickname": c.author.nickname if c.author else None,
                    "avatar_url": c.author.avatar_url if c.author else None,
                    "description": c.author.description if c.author else None,
                    "platform": c.author.platform if c.author else c.platform,
                    "fans_count": c.author.fans_count_display if c.author else "0",
                    "ip_location": c.author.ip_location if c.author else None,
                } if c.author else None,
                "comments": [
                    {
                        "id": cm.id,
                        "text": cm.comment_text,
                        "likes": cm.likes_count_num or 0,
                        "ip_location": cm.ip_location,
                        "created_at": cm.created_at.isoformat() if cm.created_at else None,
                        "user_nickname": cm.user.nickname if cm.user else None,
                    }
                    for cm in comments_list[:50]
                ],
            }
        finally:
            session.close()
