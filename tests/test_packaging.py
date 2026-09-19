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


def test_by_default_it_installs_the_latest_release_from_pypi() -> None:
    result = _run_installer()

    assert result.returncode == 0, result.stderr
    assert "source  : tyrion-cli\n" in result.stdout
    assert "github.com" not in result.stdout


def test_a_version_pins_to_that_release_on_pypi() -> None:
    result = _run_installer(env_extra={"TYRION_VERSION": "0.1.0"})
    assert "source  : tyrion-cli==0.1.0\n" in result.stdout


def test_the_development_version_installs_from_github_without_needing_git() -> None:
    result = _run_installer(env_extra={"TYRION_FROM_PYPI": "0"})

    assert "https://github.com/Xtejasveer/tyrion/archive/refs/heads/main.tar.gz" in result.stdout
    assert "git+" not in result.stdout  # a source archive, so users do not need git


def test_a_github_version_pins_to_that_release_tag() -> None:
    result = _run_installer(env_extra={"TYRION_FROM_PYPI": "0", "TYRION_VERSION": "0.1.0"})
    assert "archive/refs/tags/v0.1.0.tar.gz" in result.stdout


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


# --- what the user sees after installing (the "tyrion: command not found" bug) -----------
#
# A script cannot change the PATH of the terminal window it was started from. So when the
# install folder is not on that PATH yet, the installer must say so clearly and hand over
# one line that fixes it AND starts Tyrion.

FAKE_UV = """#!/bin/sh
# Stand-in for uv so the installer's whole flow runs offline.
case "$1 $2" in
  "tool install")
    mkdir -p "$FAKE_BIN"
    printf '#!/bin/sh\\n%s\\n' "$FAKE_TYRION_BODY" > "$FAKE_BIN/tyrion"
    if [ "${FAKE_SKIP_EXECUTABLE:-0}" != 1 ]; then chmod +x "$FAKE_BIN/tyrion"; fi
    ;;
  "tool dir") echo "$FAKE_BIN" ;;
  "tool update-shell") echo called >> "$FAKE_LOG" ;;
esac
"""


def _install_with_fake_uv(
    tmp_path: Path,
    *,
    bin_on_path: bool,
    shell: str = "/bin/zsh",
    bin_under_home: bool = True,
    tyrion_body: str = 'echo "tyrion 9.9.9"',
    skip_executable: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    home = tmp_path / "home"
    home.mkdir()
    fake_bin = home / ".local" / "bin" if bin_under_home else tmp_path / "elsewhere" / "bin"
    uv_dir = tmp_path / "uv-dir"
    uv_dir.mkdir()
    (uv_dir / "uv").write_text(FAKE_UV, encoding="utf-8")
    (uv_dir / "uv").chmod(0o755)
    log = tmp_path / "update-shell.log"

    path = [str(uv_dir), "/usr/bin", "/bin"]
    if bin_on_path:
        path.insert(1, str(fake_bin))  # the user's terminal already sees the install folder
    env = {
        "HOME": str(home),
        "PATH": os.pathsep.join(path),
        "SHELL": shell,
        "TERM": "dumb",  # no colours, so the output is plain text
        "FAKE_BIN": str(fake_bin),
        "FAKE_LOG": str(log),
        "FAKE_TYRION_BODY": tyrion_body,
        "FAKE_SKIP_EXECUTABLE": "1" if skip_executable else "0",
        "TYRION_SOURCE": "not-used-by-the-fake-uv",
    }
    result = subprocess.run(["sh", str(INSTALL_SH)], env=env, capture_output=True, text=True, check=False)
    return result, log


def test_when_the_install_folder_is_not_on_path_it_gives_one_line_that_fixes_it_and_starts_tyrion(tmp_path: Path) -> None:
    result, _ = _install_with_fake_uv(tmp_path, bin_on_path=False)

    assert result.returncode == 0, result.stderr
    assert 'export PATH="$HOME/.local/bin:$PATH" && tyrion' in result.stdout
    assert "One more step" in result.stdout


def test_that_step_is_the_last_thing_printed_so_it_cannot_be_missed(tmp_path: Path) -> None:
    result, _ = _install_with_fake_uv(tmp_path, bin_on_path=False)

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert "every new terminal window finds tyrion on its own" in lines[-1]
    # The old script printed "Get started: tyrion" right after the PATH note, which invited
    # typing `tyrion` in the very terminal that could not find it.
    assert "Get started" not in result.stdout


def test_new_terminal_windows_are_set_up_too(tmp_path: Path) -> None:
    _, log = _install_with_fake_uv(tmp_path, bin_on_path=False)

    assert log.read_text(encoding="utf-8").strip() == "called"  # uv tool update-shell ran


def test_when_it_is_already_on_path_it_just_says_how_to_start(tmp_path: Path) -> None:
    result, log = _install_with_fake_uv(tmp_path, bin_on_path=True)

    assert result.returncode == 0, result.stderr
    assert "Get started" in result.stdout
    assert "export PATH" not in result.stdout
    assert "One more step" not in result.stdout
    assert not log.exists()  # nothing to fix, so the shell profile is left alone


def test_fish_users_get_fish_syntax(tmp_path: Path) -> None:
    result, _ = _install_with_fake_uv(tmp_path, bin_on_path=False, shell="/opt/homebrew/bin/fish")

    assert "fish_add_path $HOME/.local/bin; and tyrion" in result.stdout
    assert "export PATH" not in result.stdout


def test_an_install_folder_outside_home_is_shown_as_a_full_path(tmp_path: Path) -> None:
    result, _ = _install_with_fake_uv(tmp_path, bin_on_path=False, bin_under_home=False)

    assert f'export PATH="{tmp_path}/elsewhere/bin:$PATH" && tyrion' in result.stdout


def test_a_tyrion_that_will_not_start_is_reported_not_hidden(tmp_path: Path) -> None:
    result, _ = _install_with_fake_uv(tmp_path, bin_on_path=False, tyrion_body="echo boom >&2; exit 3")

    assert result.returncode != 0
    assert "did not start" in result.stderr
    assert "One more step" not in result.stdout  # no false "you're done" message


def test_a_missing_executable_is_reported(tmp_path: Path) -> None:
    result, _ = _install_with_fake_uv(tmp_path, bin_on_path=False, skip_executable=True)

    assert result.returncode != 0
    assert "was not created" in result.stderr


# --- the documented command: works in the SAME terminal, no extra step -------------------
#
# A script cannot change the PATH of the terminal that started it, but the user's own shell can
# replace itself with a fresh login shell. So the command we tell people to run ends with
# `&& exec "$SHELL" -l`.

CURL_PART = "curl -LsSf https://raw.githubusercontent.com/Xtejasveer/tyrion/main/install.sh"
INSTALL_COMMAND = f'{CURL_PART} | sh && exec "$SHELL" -l'


def test_the_readme_and_the_script_header_show_the_same_install_command() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    header = INSTALL_SH.read_text(encoding="utf-8").splitlines()[:12]

    assert INSTALL_COMMAND in readme
    assert any(line.lstrip("# ").strip() == INSTALL_COMMAND for line in header)


def _run_documented_command(tmp_path: Path, installer_script: str) -> subprocess.CompletedProcess[str]:
    """Run the documented command with the download replaced by a stand-in installer."""
    fake_shell = tmp_path / "fake-shell"
    fake_shell.write_text('#!/bin/sh\necho "RESTARTED $*"\n', encoding="utf-8")
    fake_shell.chmod(0o755)

    command = INSTALL_COMMAND.replace(CURL_PART, f"echo '{installer_script}'")
    env = {"PATH": "/usr/bin:/bin", "SHELL": str(fake_shell)}
    return subprocess.run(
        ["sh", "-c", command + "; echo SURVIVED"], env=env, capture_output=True, text=True, check=False
    )


def test_after_a_successful_install_the_shell_restarts_as_a_login_shell(tmp_path: Path) -> None:
    result = _run_documented_command(tmp_path, "exit 0")

    assert "RESTARTED -l" in result.stdout
    assert "SURVIVED" not in result.stdout  # exec replaced the shell rather than starting a nested one


def test_if_the_install_fails_the_shell_is_left_alone(tmp_path: Path) -> None:
    result = _run_documented_command(tmp_path, "exit 1")

    assert "SURVIVED" in result.stdout  # the terminal is still there, with the error visible
    assert "RESTARTED" not in result.stdout


@pytest.mark.parametrize("shell", ["/bin/zsh", "/opt/homebrew/bin/fish"])
def test_the_fallback_also_offers_restarting_the_shell(tmp_path: Path, shell: str) -> None:
    result, _ = _install_with_fake_uv(tmp_path, bin_on_path=False, shell=shell)

    non_empty = [line for line in result.stdout.splitlines() if line.strip()]
    assert 'exec "$SHELL" -l' in result.stdout
    assert "every new terminal window finds tyrion on its own" in non_empty[-1]  # still the last thing printed
