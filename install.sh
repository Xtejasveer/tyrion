#!/bin/sh
# Tyrion installer
#
#   curl -LsSf https://raw.githubusercontent.com/Xtejasveer/tyrion/main/install.sh | sh && exec "$SHELL" -l
#
# The `&& exec "$SHELL" -l` on the end restarts your shell, so `tyrion` works in the same
# terminal right away (a script can't change the PATH of the terminal that started it, but
# your own shell can). Leave it off in scripts and CI.
#
# What this does, so you can decide before running it:
#   1. Installs `uv` (a fast Python installer, https://docs.astral.sh/uv/) if you don't have it.
#   2. Uses uv to install Tyrion into its own isolated environment. uv downloads Python
#      3.12 by itself if your machine doesn't have it.
# It never uses sudo and only writes inside your home directory.
#
# Options (environment variables):
#   TYRION_VERSION      install a specific release, for example TYRION_VERSION=0.1.0
#   TYRION_FROM_PYPI=0  install the latest development version from GitHub instead of a release
#   TYRION_SOURCE       install from somewhere else: a PyPI name, a URL, or a local folder
#   TYRION_DRY_RUN=1    show what would be done and exit without changing anything
#
# Update:     run this script again
# Uninstall:  uv tool uninstall tyrion-cli    (your ~/.tyrion data is left alone)

set -eu

REPO="Xtejasveer/tyrion"
PACKAGE="tyrion-cli"
PYTHON_VERSION="3.12"
UV_INSTALLER_URL="https://astral.sh/uv/install.sh"

# By default this installs the latest release from PyPI. Set TYRION_FROM_PYPI=0 to install
# the current development version from the GitHub source archive instead.
INSTALL_FROM_PYPI="${TYRION_FROM_PYPI:-1}"

if [ -t 1 ] && [ "${TERM:-dumb}" != "dumb" ]; then
    GOLD='\033[1;33m'
    RED='\033[1;31m'
    BOLD='\033[1m'
    DIM='\033[2m'
    RESET='\033[0m'
else
    GOLD=''
    RED=''
    BOLD=''
    DIM=''
    RESET=''
fi

say() { printf '%b\n' "$*"; }
step() { printf '%b\n' "${GOLD}›${RESET} $*"; }
fail() {
    printf '%b\n' "${RED}error:${RESET} $*" >&2
    exit 1
}

check_platform() {
    os="$(uname -s)"
    case "$os" in
        Darwin | Linux) ;;
        MINGW* | MSYS* | CYGWIN*)
            fail "Tyrion does not run natively on Windows yet.
       Install WSL (https://learn.microsoft.com/windows/wsl/install) and run this command inside it."
            ;;
        *)
            fail "Unsupported system: $os (Tyrion supports macOS and Linux)."
            ;;
    esac
}

# Where to install Tyrion from: an explicit override, the released package, or GitHub.
resolve_source() {
    if [ -n "${TYRION_SOURCE:-}" ]; then
        printf '%s' "$TYRION_SOURCE"
    elif [ "$INSTALL_FROM_PYPI" = "1" ]; then
        if [ -n "${TYRION_VERSION:-}" ]; then
            printf '%s' "$PACKAGE==$TYRION_VERSION"
        else
            printf '%s' "$PACKAGE"
        fi
    elif [ -n "${TYRION_VERSION:-}" ]; then
        printf '%s' "https://github.com/$REPO/archive/refs/tags/v$TYRION_VERSION.tar.gz"
    else
        printf '%s' "https://github.com/$REPO/archive/refs/heads/main.tar.gz"
    fi
}

ensure_uv() {
    if command -v uv >/dev/null 2>&1; then
        return
    fi

    step "Installing uv (a fast Python installer)"
    curl -LsSf "$UV_INSTALLER_URL" | sh

    # The uv installer puts it in one of these; make it visible to the rest of this script.
    for dir in "${XDG_BIN_HOME:-}" "$HOME/.local/bin" "$HOME/.cargo/bin"; do
        if [ -n "$dir" ] && [ -x "$dir/uv" ]; then
            PATH="$dir:$PATH"
            export PATH
            break
        fi
    done

    command -v uv >/dev/null 2>&1 || fail "uv was installed but could not be found. Open a new terminal and run this command again."
}

# Tyrion is installed, but the terminal window the user is typing in was opened before it
# existed, and a script can never change the PATH of the terminal that launched it. So say so
# plainly, and give ONE line that fixes PATH and starts Tyrion. New terminal windows need
# nothing, because uv adds its bin folder to the shell profile.
print_path_help() {
    dir="$1"
    case "$dir" in
        "$HOME"/*) shown="\$HOME${dir#"$HOME"}" ;;
        *) shown="$dir" ;;
    esac

    uv tool update-shell >/dev/null 2>&1 || true

    case "${SHELL:-}" in
        */fish) fix="fish_add_path $shown; and tyrion" ;;
        *) fix="export PATH=\"$shown:\$PATH\" && tyrion" ;;
    esac

    say "${GOLD}▶ One more step${RESET}"
    say "  Tyrion is installed, but this terminal window was opened before it existed and"
    say "  can't see it yet. ${BOLD}Copy and run this line${RESET} to start Tyrion right now:"
    say ""
    say "      $fix"
    say ""
    say "  Or restart your shell instead, then type tyrion:"
    say ""
    say "      exec \"\$SHELL\" -l"
    say ""
    say "  After that, every new terminal window finds ${GOLD}tyrion${RESET} on its own."
    say ""
}

main() {
    # The PATH the user's shell has right now. ensure_uv may add to PATH for this script
    # only, so we compare against this to know whether a new terminal is needed.
    original_path="$PATH"

    check_platform
    source_spec="$(resolve_source)"

    if [ "${TYRION_DRY_RUN:-0}" = "1" ]; then
        say "Tyrion installer (dry run, nothing will be changed)"
        say "  system  : $(uname -s)"
        say "  source  : $source_spec"
        say "  command : uv tool install --force --refresh --python $PYTHON_VERSION $source_spec"
        exit 0
    fi

    command -v curl >/dev/null 2>&1 || fail "curl is required but was not found."

    say ""
    say "${GOLD}◆ Installing Tyrion${RESET}"
    say ""

    ensure_uv

    step "Installing Tyrion ${DIM}(from $source_spec)${RESET}"
    uv tool install --force --refresh --python "$PYTHON_VERSION" "$source_spec"

    bin_dir="$(uv tool dir --bin 2>/dev/null || printf '%s/.local/bin' "$HOME")"
    if [ ! -x "$bin_dir/tyrion" ]; then
        fail "The install finished but $bin_dir/tyrion was not created. Run 'uv tool list' to see what was installed."
    fi

    installed="$("$bin_dir/tyrion" --version 2>&1)" || fail "Tyrion was installed but did not start: $installed"

    say ""
    say "${GOLD}✓${RESET} Installed: $installed"
    say "${DIM}Update: run this installer again    Uninstall: uv tool uninstall $PACKAGE${RESET}"
    say ""

    case ":$original_path:" in
        *":$bin_dir:"*)
            say "Get started:"
            say "    tyrion                      launch the app (it asks for an API key the first time)"
            say "    tyrion \"explain this repo\"    run a single prompt"
            say ""
            ;;
        *)
            print_path_help "$bin_dir"
            ;;
    esac
}

# Everything above only defines functions. Nothing runs until this last line, so a
# download that is cut off part-way can never execute half of the script.
main "$@"
