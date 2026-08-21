"""Discover and parse SKILLS.md files."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from tyrion_coding.resources import walk_project_roots

@dataclass(slots=True)
class Skill:
    name:str
    description: str
    body: str
    path: Path

def parse_frontmatter(text:str) -> tuple[dict[str,str], str]:
    """Parse simple YAML-like frontmatter. No PyYAML required."""

    if not text.startswith("---"):
        return {}, text
    rest = text[3:].lstrip("\n")
    end = rest.find("\n---")
    if end == -1:
        return {}, text
    raw = rest[:end]
    body = rest[end + 4 :].lstrip("\n")
    meta: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":",1)
        meta[key.strip()] = value.strip().strip("'").strip("'")
    return meta, body

def load_skill(path: Path) -> Skill:
    text = path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(text)
    name = meta.get("name") or path.parent.name
    description = meta.get("description") or ""
    return Skill(name=name, description=description, body=body.strip(), path = path)

def skill_search_dirs(cwd:str | Path) -> list[Path]:
    """Global skills first, then parent .agents/skills, then cwd (later wins)."""

    dirs = [Path.home() / ".tyrion" / "skills"]
    for root in reversed(walk_project_roots(cwd)):
        dirs.append(root / ".agents" / "skills")
    return dirs

def discover_skills(cwd: str | Path) -> list[Skill]:
    by_name: dict[str, Skill] = {}
    for directory in skill_search_dirs(cwd):
        if not directory.is_dir():
            continue
        for skill_md in sorted(directory.rglob("SKILL.md")):
            skill = load_skill(skill_md)
            by_name[skill.name] = skill
    return list(by_name.values())

def format_skills(skills:list[Skill]) -> str:
    if not skills:
        return ""
    parts = ["# Skills", ""]
    for skill in skills:
        parts.append(f"## {skill.name}")
        if skill.description:
            parts.append(skill.description)
            parts.append("")
            parts.append(skill.body)
            parts.append("")
    return "\n".join(parts).strip()
