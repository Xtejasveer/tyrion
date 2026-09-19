"""The command line: `tyrion --version` reports the installed package's version."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from typer.testing import CliRunner

from tyrion_coding import cli

runner = CliRunner()


def test_version_flag_prints_the_installed_version() -> None:
    result = runner.invoke(cli.app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == f"tyrion {version('tyrion-cli')}"


def test_the_version_is_read_from_package_metadata_not_hard_coded() -> None:
    assert cli.VERSION == version("tyrion-cli")


def test_running_from_an_uninstalled_source_tree_does_not_crash(monkeypatch) -> None:
    def missing(_name: str) -> str:
        raise PackageNotFoundError

    monkeypatch.setattr(cli, "_package_version", missing)

    assert cli._installed_version() == "0+unknown"
