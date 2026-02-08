"""XQueryBuilder — fluent API for building validated X search queries.

Three ways to build a query:
1. Fluent API:
    query = XQueryBuilder().keywords("AI agent").from_user("anthropic").has_media().build()

2. From dict (structured task payloads):
    query = XQueryBuilder.from_dict({"keywords": "AI agent", "from_user": "anthropic"}).build()

3. Raw string (validate only):
    query = XQueryBuilder.from_raw("from:anthropic AI has:media").build()

build() always calls validate_query() before returning — raises on invalid.
"""

from __future__ import annotations

from .search_rules import (
    MAX_QUERY_LENGTH,
    VALID_LANGUAGES,
    VALID_SEARCH_TABS,
    validate_query,
)


class QueryValidationError(Exception):
    """Raised when a built query fails validation."""

    def __init__(self, query: str, errors: list[str]) -> None:
        self.query = query
        self.errors = errors
        super().__init__(f"Invalid query: {'; '.join(errors)} | query={query!r}")


class XQueryBuilder:
    """Fluent builder for X search queries.

    All methods return self for chaining. Call build() to get the validated string.
    """

    def __init__(self) -> None:
        self._parts: list[str] = []
        self._search_tab: str = "Top"

    # ──────────────────────────────────────
    # Standalone operators
    # ──────────────────────────────────────

    def keywords(self, text: str) -> XQueryBuilder:
        """Add keyword(s). Multiple words are AND-ed by X."""
        self._parts.append(text)
        return self

    def exact_phrase(self, phrase: str) -> XQueryBuilder:
        """Match exact phrase (wraps in quotes)."""
        self._parts.append(f'"{phrase}"')
        return self

    def hashtag(self, tag: str) -> XQueryBuilder:
        """Match hashtag. Provide without #."""
        tag = tag.lstrip("#")
        self._parts.append(f"#{tag}")
        return self

    def cashtag(self, tag: str) -> XQueryBuilder:
        """Match cashtag (stock symbol). Provide without $."""
        tag = tag.lstrip("$")
        self._parts.append(f"${tag}")
        return self

    def from_user(self, username: str) -> XQueryBuilder:
        """Match tweets from this user."""
        username = username.lstrip("@")
        self._parts.append(f"from:{username}")
        return self

    def to_user(self, username: str) -> XQueryBuilder:
        """Match tweets replying to this user."""
        username = username.lstrip("@")
        self._parts.append(f"to:{username}")
        return self

    def mention(self, username: str) -> XQueryBuilder:
        """Match tweets mentioning this user."""
        username = username.lstrip("@")
        self._parts.append(f"@{username}")
        return self

    def url(self, url_text: str) -> XQueryBuilder:
        """Match tweets containing this URL."""
        self._parts.append(f"url:{url_text}")
        return self

    def conversation_id(self, tweet_id: str) -> XQueryBuilder:
        """Match tweets in a conversation thread."""
        self._parts.append(f"conversation_id:{tweet_id}")
        return self

    def list_id(self, lid: str) -> XQueryBuilder:
        """Match tweets from members of this list."""
        self._parts.append(f"list:{lid}")
        return self

    def place(self, place_name: str) -> XQueryBuilder:
        """Match tweets tagged with this place."""
        if " " in place_name:
            self._parts.append(f'place:"{place_name}"')
        else:
            self._parts.append(f"place:{place_name}")
        return self

    def place_country(self, country_code: str) -> XQueryBuilder:
        """Match tweets tagged in this country (ISO 3166-1 alpha-2)."""
        self._parts.append(f"place_country:{country_code.upper()}")
        return self

    # ──────────────────────────────────────
    # Conjunction-required operators
    # ──────────────────────────────────────

    def is_retweet(self) -> XQueryBuilder:
        self._parts.append("is:retweet")
        return self

    def is_reply(self) -> XQueryBuilder:
        self._parts.append("is:reply")
        return self

    def is_quote(self) -> XQueryBuilder:
        self._parts.append("is:quote")
        return self

    def is_verified(self) -> XQueryBuilder:
        self._parts.append("is:verified")
        return self

    def has_media(self) -> XQueryBuilder:
        self._parts.append("has:media")
        return self

    def has_images(self) -> XQueryBuilder:
        self._parts.append("has:images")
        return self

    def has_video(self) -> XQueryBuilder:
        self._parts.append("has:video_link")
        return self

    def has_links(self) -> XQueryBuilder:
        self._parts.append("has:links")
        return self

    def has_hashtags(self) -> XQueryBuilder:
        self._parts.append("has:hashtags")
        return self

    def has_mentions(self) -> XQueryBuilder:
        self._parts.append("has:mentions")
        return self

    def lang(self, code: str) -> XQueryBuilder:
        """Filter by language (BCP 47 code)."""
        if code not in VALID_LANGUAGES:
            raise ValueError(
                f"Invalid language code: {code!r}. "
                f"See VALID_LANGUAGES for supported codes."
            )
        self._parts.append(f"lang:{code}")
        return self

    # ──────────────────────────────────────
    # Negation operators
    # ──────────────────────────────────────

    def exclude_retweets(self) -> XQueryBuilder:
        self._parts.append("-is:retweet")
        return self

    def exclude_replies(self) -> XQueryBuilder:
        self._parts.append("-is:reply")
        return self

    def exclude_quotes(self) -> XQueryBuilder:
        self._parts.append("-is:quote")
        return self

    def exclude_links(self) -> XQueryBuilder:
        self._parts.append("-has:links")
        return self

    def exclude_keyword(self, word: str) -> XQueryBuilder:
        """Exclude tweets containing this word."""
        self._parts.append(f"-{word}")
        return self

    def exclude_from(self, username: str) -> XQueryBuilder:
        """Exclude tweets from this user."""
        username = username.lstrip("@")
        self._parts.append(f"-from:{username}")
        return self

    # ──────────────────────────────────────
    # Boolean logic
    # ──────────────────────────────────────

    def or_group(self, *terms: str) -> XQueryBuilder:
        """Add an OR group: (term1 OR term2 OR ...)."""
        if len(terms) < 2:
            raise ValueError("or_group requires at least 2 terms")
        group = " OR ".join(terms)
        self._parts.append(f"({group})")
        return self

    def raw(self, fragment: str) -> XQueryBuilder:
        """Add a raw query fragment (advanced use)."""
        self._parts.append(fragment)
        return self

    # ──────────────────────────────────────
    # Search tab
    # ──────────────────────────────────────

    def search_tab(self, tab: str) -> XQueryBuilder:
        """Set the search result tab (Top, Latest, People, Media, Lists)."""
        if tab not in VALID_SEARCH_TABS:
            raise ValueError(f"Invalid tab: {tab!r}. Valid: {sorted(VALID_SEARCH_TABS)}")
        self._search_tab = tab
        return self

    # ──────────────────────────────────────
    # Build
    # ──────────────────────────────────────

    def build(self) -> str:
        """Build and validate the query string.

        Raises:
            QueryValidationError: If the query fails validation.
        """
        query = " ".join(self._parts)
        is_valid, errors = validate_query(query)
        if not is_valid:
            raise QueryValidationError(query, errors)
        return query

    def build_with_tab(self) -> tuple[str, str]:
        """Build query and return (query_string, search_tab)."""
        return self.build(), self._search_tab

    # ──────────────────────────────────────
    # Factory: from dict
    # ──────────────────────────────────────

    @classmethod
    def from_dict(cls, d: dict) -> XQueryBuilder:
        """Build from a structured dict (e.g., task payload).

        Supported keys:
            keywords, exact_phrase, hashtag, cashtag,
            from_user, to_user, mention, url,
            conversation_id, list_id, place, place_country,
            is: list[str], has: list[str], lang,
            exclude: list[str], exclude_keywords: list[str],
            exclude_from: list[str],
            or_groups: list[list[str]],
            raw: str,
            search_tab: str
        """
        b = cls()

        # Standalone
        if v := d.get("keywords"):
            b.keywords(v)
        if v := d.get("exact_phrase"):
            b.exact_phrase(v)
        if v := d.get("hashtag"):
            b.hashtag(v)
        if v := d.get("cashtag"):
            b.cashtag(v)
        if v := d.get("from_user"):
            b.from_user(v)
        if v := d.get("to_user"):
            b.to_user(v)
        if v := d.get("mention"):
            b.mention(v)
        if v := d.get("url"):
            b.url(v)
        if v := d.get("conversation_id"):
            b.conversation_id(v)
        if v := d.get("list_id"):
            b.list_id(v)
        if v := d.get("place"):
            b.place(v)
        if v := d.get("place_country"):
            b.place_country(v)

        # Conjunction flags
        for flag in d.get("is", []):
            method = getattr(b, f"is_{flag}", None)
            if method:
                method()
        for flag in d.get("has", []):
            method_name = f"has_{flag}"
            method = getattr(b, method_name, None)
            if method:
                method()

        if v := d.get("lang"):
            b.lang(v)

        # Exclusions
        for flag in d.get("exclude", []):
            method = getattr(b, f"exclude_{flag}s", None) or getattr(b, f"exclude_{flag}", None)
            if method:
                method()
        for kw in d.get("exclude_keywords", []):
            b.exclude_keyword(kw)
        for user in d.get("exclude_from", []):
            b.exclude_from(user)

        # OR groups
        for group in d.get("or_groups", []):
            b.or_group(*group)

        # Raw fragment
        if v := d.get("raw"):
            b.raw(v)

        # Search tab
        if v := d.get("search_tab"):
            b.search_tab(v)

        return b

    # ──────────────────────────────────────
    # Factory: from raw string
    # ──────────────────────────────────────

    @classmethod
    def from_raw(cls, query: str) -> XQueryBuilder:
        """Create a builder from a raw query string (validate on build)."""
        b = cls()
        b._parts = [query]
        return b
