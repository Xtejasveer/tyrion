"""Release hygiene: what gets published, and how the one-line installer behaves."""

from __future__ import annotations

import os
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
INSTALL_SH = ROOT / "install.sh"


def _names(requirements: list[str]) -> set[str]:
    return {re.split(r"[<>=!~\[; ]", requirement, maxsplit=1)[0].lower() for requirement in requirements}


# --- what is published -------------------------------------------------------


def test_the_published_name_is_not_the_taken_pypi_name() -> None:
    # "tyrion" belongs to an unrelated project on PyPI.
    assert PYPROJECT["project"]["name"] == "tyrion-cli"


def test_the_command_users_type_is_still_tyrion() -> None:
    assert PYPROJECT["project"]["scripts"] == {"tyrion": "tyrion_coding.cli:app"}


def test_development_tools_are_not_runtime_dependencies() -> None:
    runtime = _names(PYPROJECT["project"]["dependencies"])
    assert not runtime & {"pytest", "pytest-asyncio", "pytest-aio", "ruff"}
    assert {"pytest", "pytest-asyncio", "ruff"} <= _names(PYPROJECT["dependency-groups"]["dev"])


def test_the_app_needs_what_it_imports() -> None:
    runtime = _names(PYPROJECT["project"]["dependencies"])
    assert {"textual", "typer", "httpx", "pydantic", "rich", "pygments"} <= runtime


def test_the_project_has_real_metadata() -> None:
    project = PYPROJECT["project"]
    assert "Add your description here" not in project["description"]
    assert len(project["description"]) > 20
    assert project["license"] == "MIT"
    assert project["requires-python"] == ">=3.12"
    assert project["urls"]["Repository"].startswith("https://github.com/")


def test_the_license_file_exists_and_is_mit() -> None:
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert text.startswith("MIT License")
    assert "Permission is hereby granted" in text


def test_everything_the_wheel_lists_exists() -> None:
    wheel = PYPROJECT["tool"]["hatch"]["build"]["targets"]["wheel"]
    for package in wheel["packages"]:
        assert (ROOT / package / "__init__.py").is_file(), package
    for source in wheel["force-include"]:
        assert (ROOT / source).is_file(), source


def test_scratch_files_are_not_shipped_in_the_source_archive() -> None:
    included = PYPROJECT["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    assert "/src" in included and "/README.md" in included and "/LICENSE" in included
    for scratch in ("main.py", "fix_renderer.py", "assets", ".DS_Store"):
        assert not any(scratch in entry for entry in included), scratch


def test_python_version_claims_agree() -> None:
    # The interpreter the project pins for development is one it also supports.
    pinned = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert pinned.startswith("3.12")


# --- the one-line installer --------------------------------------------------


def _run_installer(*, env_extra: dict[str, str] | None = None, path_prefix: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "TYRION_DRY_RUN": "1", **(env_extra or {})}
    for name in ("TYRION_SOURCE", "TYRION_VERSION", "TYRION_FROM_PYPI"):
        if env_extra is None or name not in env_extra:
            env.pop(name, None)  # start from a clean slate
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env['PATH']}"
    return subprocess.run(["sh", str(INSTALL_SH)], env=env, capture_output=True, text=True, check=False)


def test_the_installer_is_valid_shell() -> None:
    result = subprocess.run(["sh", "-n", str(INSTALL_SH)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_the_installer_only_runs_on_its_last_line() -> None:
    # A download that is cut off part-way must not execute half a script.
    lines = INSTALL_SH.read_text(encoding="utf-8").splitlines()
    assert lines[-1] == 'main "$@"'
    top_level_calls = [
        line for line in lines[:-1]
        if line and not line.startswith((" ", "\t", "#", "}")) and "()" not in line
    ]  # fmt: skip
    for line in top_level_calls:  # only assignments, set, and control flow before that
        assert re.match(r"^(set |[A-Z_]+=|if |else|elif |fi$)", line), f"runs at top level: {line!r}"


def test_the_installer_never_uses_sudo() -> None:
    code = [line for line in INSTALL_SH.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#")]
    assert not any("sudo" in line for line in code)


def test_the_installer_stops_on_errors_and_unset_variables() -> None:
    assert "set -eu" in INSTALL_SH.read_text(encoding="utf-8")


def test_by_default_it_installs_from_github_without_needing_git() -> None:
    result = _run_installer()

    assert result.returncode == 0, result.stderr
    assert "https://github.com/Xtejasveer/tyrion/archive/refs/heads/main.tar.gz" in result.stdout
    assert "git+" not in result.stdout  # a source archive, so users do not need git


def test_a_version_pins_to_that_release_tag() -> None:
    result = _run_installer(env_extra={"TYRION_VERSION": "0.1.0"})
    assert "archive/refs/tags/v0.1.0.tar.gz" in result.stdout


def test_once_published_it_can_install_the_pypi_package() -> None:
    latest = _run_installer(env_extra={"TYRION_FROM_PYPI": "1"})
    pinned = _run_installer(env_extra={"TYRION_FROM_PYPI": "1", "TYRION_VERSION": "0.2.0"})
    assert "source  : tyrion-cli\n" in latest.stdout
    assert "source  : tyrion-cli==0.2.0\n" in pinned.stdout


def test_an_explicit_source_beats_everything() -> None:
    result = _run_installer(
        env_extra={"TYRION_SOURCE": "/some/folder", "TYRION_VERSION": "9.9.9", "TYRION_FROM_PYPI": "1"}
    )
    assert "source  : /some/folder\n" in result.stdout


def test_a_dry_run_changes_nothing() -> None:
    result = _run_installer()
    assert "dry run" in result.stdout
    assert "Installing uv" not in result.stdout  # it never got as far as installing anything


@pytest.mark.parametrize(
    ("uname", "message"),
    [
        ("MINGW64_NT-10.0", "WSL"),  # Windows: point people at WSL
        ("MSYS_NT-10.0", "WSL"),
        ("FreeBSD", "Unsupported system: FreeBSD"),
    ],
)
def test_unsupported_systems_get_a_clear_message_and_a_failure_exit(tmp_path: Path, uname: str, message: str) -> None:
    fake = tmp_path / "uname"
    fake.write_text(f"#!/bin/sh\necho {uname}\n", encoding="utf-8")
    fake.chmod(0o755)

    result = _run_installer(path_prefix=tmp_path)

    assert result.returncode != 0
    assert message in result.stderr


@pytest.mark.parametrize("system", ["Darwin", "Linux"])
def test_macos_and_linux_are_supported(tmp_path: Path, system: str) -> None:
    fake = tmp_path / "uname"
    fake.write_text(f"#!/bin/sh\necho {system}\n", encoding="utf-8")
    fake.chmod(0o755)

    result = _run_installer(path_prefix=tmp_path)

    assert result.returncode == 0, result.stderr
    assert system in result.stdout
