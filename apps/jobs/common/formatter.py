"""Custom log formatter for Asia/Shanghai timezone display.

This formatter is used across all jobs to provide consistent timezone display
while the database stores timestamps in UTC.
"""

import logging
from datetime import datetime, timedelta, timezone


class ShanghaiFormatter(logging.Formatter):
    """Formats log timestamps in Asia/Shanghai timezone for better readability.

    Database Strategy:
    - Database: Stores timestamps in UTC (best practice)
    - Logger: Displays times in Asia/Shanghai (UTC+8) for user-friendliness
    """

    def formatTime(self, record, datefmt=None):
        """Convert UTC timestamp to Shanghai time (UTC+8)."""
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        shanghai_time = dt + timedelta(hours=8)
        if datefmt:
            return shanghai_time.strftime(datefmt)
        return shanghai_time.strftime('%Y-%m-%d %H:%M:%S')
