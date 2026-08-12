"""CLI entry point for tyrion"""

import typer

app = typer.Typer(add_completion=False)

@app.command()
def main(
    version: bool = typer.Option(False, "--version","-v", help = "Show version and exit."),
) ->None:
    """A terminal coding agent"""
    if version:
        print("tyrion 0.1.0")
        raise typer.Exit()

if __name__ == "__main__":
    app()