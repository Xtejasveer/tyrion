from __future__ import annotations

from pathlib import Path

from tyrion_coding.skills import discover_skills
from tyrion_coding.system_prompt import assemble_system_prompt


def test_template_includes_runtime_and_tools(tmp_path: Path) -> None:
    prompt = assemble_system_prompt(cwd=tmp_path, tools=[], os_name="Darwin")
    assert "tyrion" in prompt
    assert str(tmp_path.resolve()) in prompt
    assert "Darwin" in prompt
    assert "(no tools available)" in prompt
    assert "AGENTS.md" not in prompt


def test_agents_md_is_appended(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("Always use type hints.\n", encoding="utf-8")
    prompt = assemble_system_prompt(cwd=tmp_path, tools=[], os_name="Darwin")
    assert "Project instructions" in prompt
    assert "Always use type hints." in prompt


def test_skill_discovery(tmp_path: Path) -> None:
    skill_dir = tmp_path / ".agents" / "skills" / "commit"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: commit\ndescription: Write git commits\n---\nUse conventional commits.\n",
        encoding="utf-8",
    )
    skills = discover_skills(tmp_path)
    assert [skill.name for skill in skills] == ["commit"]

    prompt = assemble_system_prompt(cwd=tmp_path, tools=[], os_name="Darwin")
    assert "# Skills" in prompt
    assert "Use conventional commits." in prompt