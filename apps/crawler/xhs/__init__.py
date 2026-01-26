from apps.crawler.registry import register_crawler
from apps.crawler.xhs.scraper import XhsCrawler

register_crawler("xhs", XhsCrawler)
