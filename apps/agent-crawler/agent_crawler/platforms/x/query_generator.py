"""AI-powered query generator for X search (hybrid mode).

Uses Grok LLM to convert natural language intent into a valid X search query.
The system prompt includes all X search rules from search_rules.py, ensuring
the AI only uses valid operators and syntax.

Flow:
1. Receive intent string (e.g., "找 Elon 关于 AI 的带图推文")
2. Send to Grok with X search rules as system prompt
3. Grok returns a query string
4. Validate via validate_query()
5. If invalid, retry once with error feedback
6. Return valid query or raise QueryGenerationError
"""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from .errors import QueryGenerationError
from .search_rules import get_rules_for_prompt, validate_query

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = f"""\
You are an X (Twitter) search query builder. Your ONLY job is to convert
a user's intent into a valid X search query string.

{get_rules_for_prompt()}

## Instructions
- Output ONLY the query string, nothing else. No explanation, no markdown, no quotes.
- Use the operators above. Do not invent operators.
- Combine operators with spaces (implicit AND).
- Use OR for alternatives, parentheses for grouping.
- Prefer concise queries. Do not over-constrain.
- If the intent is in a non-English language, still build the query using
  X operators (which are in English). Add lang: if the user wants results
  in a specific language.

## Examples
Intent: "Elon Musk 关于 AI 的带图片推文"
Query: from:elonmusk AI has:images

Intent: "recent AI research papers shared on twitter in English"
Query: AI (paper OR research OR arxiv) has:links lang:en -is:retweet

Intent: "anthropic or openai announcements with media"
Query: (from:anthropic OR from:OpenAI) has:media -is:retweet
"""

MAX_RETRIES = 1


class QueryGenerator:
    """Generate X search queries from natural language intent using Grok."""

    def __init__(self, llm: AsyncOpenAI, model: str) -> None:
        self._llm = llm
        self._model = model

    async def generate(self, intent: str) -> str:
        """Convert intent to a validated X search query.

        Args:
            intent: Natural language description of what to search for.

        Returns:
            Valid X search query string.

        Raises:
            QueryGenerationError: If AI fails to produce a valid query.
        """
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": intent},
        ]

        for attempt in range(1 + MAX_RETRIES):
            response = await self._llm.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=0.3,
                max_tokens=200,
            )
            query = (response.choices[0].message.content or "").strip()
            # Strip markdown code fences if LLM wraps output
            if query.startswith("```") and query.endswith("```"):
                query = query[3:-3].strip()
            if query.startswith("`") and query.endswith("`"):
                query = query[1:-1].strip()

            logger.info(
                "QueryGenerator attempt %d: intent=%r → query=%r",
                attempt + 1, intent, query,
            )

            is_valid, errors = validate_query(query)
            if is_valid:
                return query

            # Retry with error feedback
            logger.warning(
                "QueryGenerator validation failed (attempt %d): %s",
                attempt + 1, errors,
            )
            messages.append({"role": "assistant", "content": query})
            messages.append({
                "role": "user",
                "content": (
                    f"That query is invalid. Errors: {'; '.join(errors)}. "
                    "Please fix and output ONLY the corrected query string."
                ),
            })

        raise QueryGenerationError(
            f"Failed to generate valid query after {1 + MAX_RETRIES} attempts. "
            f"Intent: {intent!r}, Last query: {query!r}, Errors: {errors}"
        )
