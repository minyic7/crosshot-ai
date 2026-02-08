"""X (Twitter) search rules — structured operator schema.

This file is the single source of truth for X search query syntax.
It serves three purposes:
1. Human-readable reference for all X search operators
2. AI-consumable via get_rules_for_prompt() — fed to LLM for query generation
3. Validation source via validate_query() — validates AI/human-generated queries

All operators sourced from:
- https://developer.x.com/en/docs/x-api/tweets/search/integrate/build-a-query
- https://developer.x.com/en/docs/x-api/enterprise/rules-and-filtering/operators
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class OperatorType(str, Enum):
    """Whether an operator can stand alone or needs a standalone companion."""
    STANDALONE = "standalone"
    CONJUNCTION = "conjunction_required"


class ValueType(str, Enum):
    """The kind of value an operator expects."""
    NONE = "none"              # e.g. has:media (no user value)
    KEYWORD = "keyword"        # free-text keyword
    USERNAME = "username"      # @-less username
    PHRASE = "phrase"          # quoted exact phrase
    URL = "url"               # partial or full URL
    LANG_CODE = "lang_code"   # BCP 47 language code
    TWEET_ID = "tweet_id"     # numeric tweet ID
    LIST_ID = "list_id"       # numeric list ID
    PLACE = "place"           # place name (quoted if multi-word)
    COUNTRY_CODE = "country_code"  # ISO 3166-1 alpha-2
    EMOJI = "emoji"           # emoji character
    HASHTAG = "hashtag"       # hashtag without #
    CASHTAG = "cashtag"       # cashtag without $


@dataclass(frozen=True)
class SearchOperator:
    """A single X search operator with full metadata."""
    name: str
    syntax: str
    description: str
    op_type: OperatorType
    value_type: ValueType = ValueType.NONE
    negatable: bool = True
    examples: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────
# Standalone operators (can be used alone)
# ──────────────────────────────────────────────

STANDALONE_OPERATORS: list[SearchOperator] = [
    SearchOperator(
        name="keyword",
        syntax="{word}",
        description="Match tweets containing this word. Multiple words are AND-ed.",
        op_type=OperatorType.STANDALONE,
        value_type=ValueType.KEYWORD,
        examples=["AI", "machine learning"],
    ),
    SearchOperator(
        name="exact_phrase",
        syntax='"{phrase}"',
        description="Match tweets containing this exact phrase.",
        op_type=OperatorType.STANDALONE,
        value_type=ValueType.PHRASE,
        examples=['"machine learning"', '"artificial intelligence"'],
    ),
    SearchOperator(
        name="hashtag",
        syntax="#{hashtag}",
        description="Match tweets containing this hashtag.",
        op_type=OperatorType.STANDALONE,
        value_type=ValueType.HASHTAG,
        examples=["#AI", "#MachineLearning"],
    ),
    SearchOperator(
        name="cashtag",
        syntax="${cashtag}",
        description="Match tweets containing this cashtag (stock symbol).",
        op_type=OperatorType.STANDALONE,
        value_type=ValueType.CASHTAG,
        examples=["$TSLA", "$AAPL"],
    ),
    SearchOperator(
        name="from",
        syntax="from:{username}",
        description="Match tweets posted by this user.",
        op_type=OperatorType.STANDALONE,
        value_type=ValueType.USERNAME,
        examples=["from:elonmusk", "from:anthropic"],
    ),
    SearchOperator(
        name="to",
        syntax="to:{username}",
        description="Match tweets that are replies to this user.",
        op_type=OperatorType.STANDALONE,
        value_type=ValueType.USERNAME,
        examples=["to:elonmusk"],
    ),
    SearchOperator(
        name="mention",
        syntax="@{username}",
        description="Match tweets mentioning this user.",
        op_type=OperatorType.STANDALONE,
        value_type=ValueType.USERNAME,
        examples=["@anthropic"],
    ),
    SearchOperator(
        name="url",
        syntax="url:{url}",
        description="Match tweets containing this URL (partial match works).",
        op_type=OperatorType.STANDALONE,
        value_type=ValueType.URL,
        examples=["url:anthropic.com", 'url:"https://arxiv.org"'],
    ),
    SearchOperator(
        name="conversation_id",
        syntax="conversation_id:{tweet_id}",
        description="Match tweets in this conversation thread.",
        op_type=OperatorType.STANDALONE,
        value_type=ValueType.TWEET_ID,
        negatable=False,
        examples=["conversation_id:1234567890"],
    ),
    SearchOperator(
        name="list",
        syntax="list:{list_id}",
        description="Match tweets from members of this list.",
        op_type=OperatorType.STANDALONE,
        value_type=ValueType.LIST_ID,
        examples=["list:123456"],
    ),
    SearchOperator(
        name="place",
        syntax="place:{place_name}",
        description="Match tweets tagged with this place.",
        op_type=OperatorType.STANDALONE,
        value_type=ValueType.PLACE,
        examples=["place:seattle", 'place:"new york city"'],
    ),
    SearchOperator(
        name="place_country",
        syntax="place_country:{country_code}",
        description="Match tweets tagged with a place in this country (ISO 3166-1 alpha-2).",
        op_type=OperatorType.STANDALONE,
        value_type=ValueType.COUNTRY_CODE,
        examples=["place_country:US", "place_country:JP"],
    ),
]

# ──────────────────────────────────────────────
# Conjunction-required operators (need a standalone companion)
# ──────────────────────────────────────────────

CONJUNCTION_OPERATORS: list[SearchOperator] = [
    SearchOperator(
        name="is:retweet",
        syntax="is:retweet",
        description="Match retweets. Must be combined with a standalone operator.",
        op_type=OperatorType.CONJUNCTION,
        examples=["from:elonmusk is:retweet"],
    ),
    SearchOperator(
        name="is:reply",
        syntax="is:reply",
        description="Match replies. Must be combined with a standalone operator.",
        op_type=OperatorType.CONJUNCTION,
        examples=["from:elonmusk is:reply"],
    ),
    SearchOperator(
        name="is:quote",
        syntax="is:quote",
        description="Match quote tweets. Must be combined with a standalone operator.",
        op_type=OperatorType.CONJUNCTION,
        examples=["#AI is:quote"],
    ),
    SearchOperator(
        name="is:verified",
        syntax="is:verified",
        description="Match tweets from verified (blue check) accounts.",
        op_type=OperatorType.CONJUNCTION,
        examples=["AI is:verified"],
    ),
    SearchOperator(
        name="has:media",
        syntax="has:media",
        description="Match tweets containing any media (images, video, GIF).",
        op_type=OperatorType.CONJUNCTION,
        examples=["AI has:media"],
    ),
    SearchOperator(
        name="has:images",
        syntax="has:images",
        description="Match tweets containing images.",
        op_type=OperatorType.CONJUNCTION,
        examples=["from:NASA has:images"],
    ),
    SearchOperator(
        name="has:video_link",
        syntax="has:video_link",
        description="Match tweets containing video (including YouTube links).",
        op_type=OperatorType.CONJUNCTION,
        examples=["#tutorial has:video_link"],
    ),
    SearchOperator(
        name="has:links",
        syntax="has:links",
        description="Match tweets containing any links.",
        op_type=OperatorType.CONJUNCTION,
        examples=["AI has:links"],
    ),
    SearchOperator(
        name="has:hashtags",
        syntax="has:hashtags",
        description="Match tweets containing at least one hashtag.",
        op_type=OperatorType.CONJUNCTION,
        examples=["from:elonmusk has:hashtags"],
    ),
    SearchOperator(
        name="has:mentions",
        syntax="has:mentions",
        description="Match tweets containing at least one @mention.",
        op_type=OperatorType.CONJUNCTION,
        examples=["AI has:mentions"],
    ),
    SearchOperator(
        name="lang",
        syntax="lang:{lang_code}",
        description="Match tweets in this language (BCP 47 code).",
        op_type=OperatorType.CONJUNCTION,
        value_type=ValueType.LANG_CODE,
        negatable=False,
        examples=["AI lang:en", "AI lang:ja"],
    ),
]

ALL_OPERATORS: list[SearchOperator] = STANDALONE_OPERATORS + CONJUNCTION_OPERATORS

# Operator names that are valid in queries
_KNOWN_PREFIX_OPS = {op.name.split(":")[0] for op in ALL_OPERATORS if ":" in op.name}
_KNOWN_PREFIX_OPS.update({"from", "to", "url", "conversation_id", "list",
                           "place", "place_country", "lang", "is", "has"})

# ──────────────────────────────────────────────
# Valid language codes (BCP 47 subset supported by X)
# ──────────────────────────────────────────────

VALID_LANGUAGES = frozenset({
    "am", "ar", "bg", "bn", "bo", "ca", "ckb", "cs", "cy", "da", "de",
    "el", "en", "es", "et", "eu", "fa", "fi", "fr", "gu", "he", "hi",
    "hr", "hu", "hy", "id", "is", "it", "ja", "ka", "km", "kn", "ko",
    "lo", "lt", "lv", "ml", "mr", "ms", "my", "ne", "nl", "no", "or",
    "pa", "pl", "ps", "pt", "ro", "ru", "sd", "si", "sk", "sl", "sr",
    "sv", "ta", "te", "th", "tl", "tr", "uk", "ur", "vi", "zh",
    # X also supports undetermined
    "und",
})

# ──────────────────────────────────────────────
# Search result types (tab selection on x.com/search)
# ──────────────────────────────────────────────

VALID_SEARCH_TABS = frozenset({"Top", "Latest", "People", "Media", "Lists"})

# Query constraints
MAX_QUERY_LENGTH = 512


# ──────────────────────────────────────────────
# Rules serializer for AI prompts
# ──────────────────────────────────────────────

def get_rules_for_prompt() -> str:
    """Serialize all X search rules into a text block for LLM system prompts.

    Returns a human-readable reference that an LLM can use to build valid queries.
    """
    lines = [
        "# X (Twitter) Search Query Rules",
        "",
        "## Standalone Operators (can be used alone)",
        "",
    ]
    for op in STANDALONE_OPERATORS:
        neg = " (can negate with -)" if op.negatable else ""
        lines.append(f"- `{op.syntax}` — {op.description}{neg}")
        if op.examples:
            lines.append(f"  Examples: {', '.join(op.examples)}")

    lines.extend([
        "",
        "## Conjunction-Required Operators (MUST be combined with a standalone operator)",
        "",
    ])
    for op in CONJUNCTION_OPERATORS:
        neg = " (can negate with -)" if op.negatable else ""
        lines.append(f"- `{op.syntax}` — {op.description}{neg}")
        if op.examples:
            lines.append(f"  Examples: {', '.join(op.examples)}")

    lines.extend([
        "",
        "## Boolean Logic",
        "- AND: separate terms with space (implicit AND)",
        "- OR: use `OR` keyword between terms (must be uppercase)",
        "- NOT: prefix with `-` (e.g., `-is:retweet`, `-from:bot`)",
        "- Grouping: use parentheses `()` for complex logic",
        "  Example: `(AI OR ML) from:anthropic -is:retweet`",
        "",
        "## Constraints",
        f"- Maximum query length: {MAX_QUERY_LENGTH} characters",
        "- Conjunction operators (is:, has:, lang:) MUST appear with at least one standalone operator",
        "- Parentheses must be balanced",
        "- lang: codes must be valid BCP 47 (e.g., en, ja, zh, es, fr, de, ko, pt, ru)",
        "",
        "## Search Tabs",
        f"- Available: {', '.join(sorted(VALID_SEARCH_TABS))}",
        "- Default: Top (most relevant)",
        "- Latest: chronological order",
    ])
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Query validation
# ──────────────────────────────────────────────

# Regex patterns for operator extraction
_OP_PATTERN = re.compile(
    r"""
    (?:^|(?<=\s))           # start of string or preceded by space
    (-?)                    # optional negation
    (?:
        (is|has|lang|from|to|url|conversation_id|list|place_country|place)
        :
        ("[^"]*"|\S+)       # value: quoted or unquoted
    )
    """,
    re.VERBOSE,
)

# Known is: / has: values
_VALID_IS_VALUES = frozenset({"retweet", "reply", "quote", "verified"})
_VALID_HAS_VALUES = frozenset({"media", "images", "video_link", "links", "hashtags", "mentions"})


def validate_query(query: str) -> tuple[bool, list[str]]:
    """Validate an X search query string against the rules.

    Returns:
        (is_valid, errors) — True with empty list if valid,
        False with list of error descriptions if invalid.
    """
    errors: list[str] = []
    query = query.strip()

    if not query:
        return False, ["Query is empty"]

    # Length check
    if len(query) > MAX_QUERY_LENGTH:
        errors.append(f"Query is {len(query)} chars, max is {MAX_QUERY_LENGTH}")

    # Balanced parentheses
    depth = 0
    for ch in query:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth < 0:
            errors.append("Unbalanced parentheses: unexpected ')'")
            break
    if depth > 0:
        errors.append(f"Unbalanced parentheses: {depth} unclosed '('")

    # Empty groups
    if "()" in query:
        errors.append("Empty parentheses group '()' not allowed")

    # Extract and validate operators
    has_standalone = False
    has_conjunction = False

    # Check for standalone content (keywords, hashtags, from:, to:, etc.)
    standalone_prefixes = {"from", "to", "url", "conversation_id", "list", "place", "place_country"}
    for match in _OP_PATTERN.finditer(query):
        _neg, prefix, value = match.groups()
        value = value.strip('"')

        if prefix in standalone_prefixes:
            has_standalone = True

        if prefix == "is":
            has_conjunction = True
            if value not in _VALID_IS_VALUES:
                errors.append(
                    f"Invalid is:{value}. Valid: {', '.join(sorted(_VALID_IS_VALUES))}"
                )

        elif prefix == "has":
            has_conjunction = True
            if value not in _VALID_HAS_VALUES:
                errors.append(
                    f"Invalid has:{value}. Valid: {', '.join(sorted(_VALID_HAS_VALUES))}"
                )

        elif prefix == "lang":
            has_conjunction = True
            if value not in VALID_LANGUAGES:
                errors.append(
                    f"Invalid lang:{value}. Must be a valid BCP 47 code "
                    f"(e.g., en, ja, zh, es, fr)"
                )

    # Check for bare keywords/phrases/hashtags/mentions (standalone content)
    # Remove all operator expressions, boolean keywords, and parens to find remaining tokens
    remaining = _OP_PATTERN.sub("", query)
    remaining = re.sub(r"\b(OR|AND)\b", "", remaining)
    remaining = re.sub(r"[()]", "", remaining)
    remaining = remaining.strip()
    if remaining:
        has_standalone = True

    # Conjunction requires standalone
    if has_conjunction and not has_standalone:
        errors.append(
            "Conjunction operators (is:, has:, lang:) require at least one "
            "standalone operator (keyword, from:, to:, hashtag, etc.)"
        )

    return (len(errors) == 0, errors)
