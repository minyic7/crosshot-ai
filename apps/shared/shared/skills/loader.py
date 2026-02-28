"""SkillLoader — reads skill markdown files and parses YAML frontmatter."""

import logging
from pathlib import Path

import yaml

from shared.skills.models import Skill

logger = logging.getLogger(__name__)


class SkillLoader:
    """Load skills from markdown files in a directory.

    Each .md file can have optional YAML frontmatter between --- delimiters:

        ---
        name: deep_dive
        description: Analyze new content and extract key findings
        routes_to: [crawler, searcher]
        ---
        # Deep Dive Analysis
        [prompt instructions here]

    If no frontmatter is present, the filename (without .md) is used as the name.
    """

    @staticmethod
    def load(skills_dir: str | Path) -> list[Skill]:
        """Load all .md files from the given directory as Skills."""
        skills_path = Path(skills_dir)
        if not skills_path.is_dir():
            logger.warning("Skills directory not found: %s", skills_path)
            return []

        skills: list[Skill] = []
        for md_file in sorted(skills_path.glob("*.md")):
            try:
                skill = SkillLoader._parse_skill_file(md_file)
                skills.append(skill)
                logger.debug("Loaded skill: %s from %s", skill.name, md_file.name)
            except Exception:
                logger.warning("Failed to parse skill file: %s", md_file, exc_info=True)

        logger.info("Loaded %d skills from %s", len(skills), skills_path)
        return skills

    @staticmethod
    def _parse_skill_file(path: Path) -> Skill:
        """Parse a single skill markdown file."""
        raw = path.read_text(encoding="utf-8")
        meta, body = SkillLoader._split_frontmatter(raw)

        return Skill(
            name=meta.get("name", path.stem),
            description=meta.get("description", ""),
            routes_to=meta.get("routes_to", []),
            prompt_text=body.strip(),
        )

    @staticmethod
    def _split_frontmatter(text: str) -> tuple[dict, str]:
        """Split YAML frontmatter from markdown body.

        Returns (metadata_dict, body_text). If no frontmatter, returns ({}, full_text).
        """
        stripped = text.strip()
        if not stripped.startswith("---"):
            return {}, text

        # Find the closing ---
        end_idx = stripped.find("---", 3)
        if end_idx == -1:
            return {}, text

        frontmatter_str = stripped[3:end_idx].strip()
        body = stripped[end_idx + 3 :]

        try:
            meta = yaml.safe_load(frontmatter_str) or {}
        except yaml.YAMLError:
            logger.warning("Invalid YAML frontmatter, ignoring")
            meta = {}

        if not isinstance(meta, dict):
            meta = {}

        return meta, body
