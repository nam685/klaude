"""Skills — reusable prompt templates invoked via /skill_name.

A skill is a markdown file with YAML frontmatter that defines a reusable
prompt template. When invoked, the skill body is injected as a user message
into the conversation, and the LLM follows those instructions.

Skill file format (.klaude/skills/*.md):

    ---
    name: commit
    description: Smart git commit with meaningful message
    ---
    Analyze the current git changes with git_status and git_diff.
    Write a clear, concise commit message that explains the "why" not the "what".
    Then use git_commit to commit the changes.

    {input}

Parameters:
    {input}  — everything the user typed after /skill_name
    {cwd}    — current working directory

Skills are loaded from two sources:
    1. Built-in skills (hardcoded in this module)
    2. User skills from .klaude/skills/*.md (override built-ins with same name)

See Note 34 in docs/07-implementation-notes.md.
"""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Skill:
    """A reusable prompt template."""

    name: str
    description: str
    body: str  # The prompt text (markdown after frontmatter)

    def render(self, user_input: str = "") -> str:
        """Render the skill body with parameter substitution."""
        text = self.body
        text = text.replace("{input}", user_input)
        text = text.replace("{cwd}", os.getcwd())
        # Clean up blank lines from empty {input}
        if not user_input:
            while "\n\n\n" in text:
                text = text.replace("\n\n\n", "\n\n")
        return text.strip()


# ---------------------------------------------------------------------------
# Built-in skills
# ---------------------------------------------------------------------------

_BUILTIN_SKILLS: list[Skill] = [
    Skill(
        name="commit",
        description="Smart git commit — analyze changes and write a meaningful message",
        body="""\
Analyze the current git changes:
1. Run git_status to see what's changed.
2. Run git_diff to see the actual changes.
3. Write a clear, concise commit message that explains the "why" not just the "what".
4. Use git_commit to commit the changes.

If there are no changes to commit, say so.

{input}""",
    ),
    Skill(
        name="review",
        description="Code review — analyze recent changes for issues",
        body="""\
Review the current code changes for quality, bugs, and improvements:
1. Run git_diff to see what's changed (or git_diff with target="HEAD~1" if nothing is staged).
2. For each changed file, analyze:
   - Correctness: any bugs or logic errors?
   - Style: consistent with the codebase?
   - Security: any vulnerabilities introduced?
   - Performance: any obvious inefficiencies?
3. Give a concise summary: what's good, what needs attention.
   Be specific — reference file names and line numbers.

{input}""",
    ),
    Skill(
        name="explain",
        description="Explain codebase — understand project structure and code",
        body="""\
Explain this codebase (or the specified part of it):
1. Start with list_directory to see the project structure.
2. Read key files (README, main entry point, config).
3. Summarize: what does this project do, how is it organized,
   what are the main components and how do they connect?
4. Keep it concise but thorough enough to onboard someone new.

{input}""",
    ),
]


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse YAML frontmatter from a markdown string.

    Returns (metadata_dict, body_text). If no frontmatter, metadata is empty.
    We parse the simple key: value format ourselves to avoid a PyYAML dependency.
    """
    if not text.startswith("---"):
        return {}, text

    # Find closing ---
    end = text.find("---", 3)
    if end == -1:
        return {}, text

    # Extract frontmatter lines
    fm_text = text[3:end].strip()
    body = text[end + 3 :].strip()

    metadata: dict[str, str] = {}
    for line in fm_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip()

    return metadata, body


def load_user_skills(skills_dir: str) -> list[Skill]:
    """Load user-defined skills from .md files in the skills directory."""
    skills_path = Path(skills_dir)
    if not skills_path.is_dir():
        return []

    skills: list[Skill] = []
    for md_file in sorted(skills_path.glob("*.md")):
        if md_file.name.startswith("_"):
            continue
        try:
            text = md_file.read_text(encoding="utf-8")
            metadata, body = _parse_frontmatter(text)
            name = metadata.get("name", md_file.stem)
            description = metadata.get("description", f"User skill: {name}")
            skills.append(Skill(name=name, description=description, body=body))
        except Exception:
            # Skip broken skill files
            continue

    return skills


def load_all_skills(skills_dir: str = ".klaude/skills") -> dict[str, Skill]:
    """Load all skills: built-ins first, then user skills (which can override).

    Returns a dict keyed by skill name.
    """
    result: dict[str, Skill] = {}

    # Built-in skills first
    for skill in _BUILTIN_SKILLS:
        result[skill.name] = skill

    # User skills override built-ins with the same name
    for skill in load_user_skills(skills_dir):
        result[skill.name] = skill

    return result


def format_skill_list(skills: dict[str, Skill]) -> str:
    """Format skills for display in the REPL."""
    if not skills:
        return "No skills available."

    lines = ["Available skills:"]
    for name in sorted(skills):
        skill = skills[name]
        lines.append(f"  /{name:16s} {skill.description}")
    lines.append("")
    lines.append("Usage: /skill_name [optional input]")
    return "\n".join(lines)
