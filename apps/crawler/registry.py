from apps.crawler.base import BaseCrawler

_registry: dict[str, type[BaseCrawler]] = {}


def register_crawler(platform: str, crawler_class: type[BaseCrawler]) -> None:
    _registry[platform] = crawler_class


def get_crawler(platform: str) -> type[BaseCrawler] | None:
    return _registry.get(platform)
