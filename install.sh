#!/bin/sh
# Tyrion installer
#
#   curl -LsSf https://raw.githubusercontent.com/Xtejasveer/tyrion/main/install.sh | sh
#
# What this does, so you can decide before running it:
#   1. Installs `uv` (a fast Python installer, https://docs.astral.sh/uv/) if you don't have it.
#   2. Uses uv to install Tyrion into its own isolated environment. uv downloads Python
#      3.12 by itself if your machine doesn't have it.
# It never uses sudo and only writes inside your home directory.
#
# Options (environment variables):
#   TYRION_VERSION   install a specific release, for example TYRION_VERSION=0.1.0
#   TYRION_SOURCE    install from somewhere else: a PyPI name, a URL, or a local folder
#   TYRION_DRY_RUN=1 show what would be done and exit without changing anything
#
# Update:     run this script again
# Uninstall:  uv tool uninstall tyrion-cli    (your ~/.tyrion data is left alone)

set -eu

REPO="Xtejasveer/tyrion"
PACKAGE="tyrion-cli"
PYTHON_VERSION="3.12"
UV_INSTALLER_URL="https://astral.sh/uv/install.sh"

# Until the first release is on PyPI, install from the GitHub source archive. After
# publishing, change the default below to 1 and this installs the released package.
INSTALL_FROM_PYPI="${TYRION_FROM_PYPI:-0}"

if [ -t 1 ] && [ "${TERM:-dumb}" != "dumb" ]; then
    GOLD='\033[1;33m'
    RED='\033[1;31m'
    DIM='\033[2m'
    RESET='\033[0m'
else
    GOLD=''
    RED=''
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
    say ""

    case ":$original_path:" in
        *":$bin_dir:"*) ;;
        *)
            # Not on the user's PATH yet. Let uv add it to their shell profile, and tell
            # them how to use Tyrion in this very terminal.
            uv tool update-shell >/dev/null 2>&1 || true
            say "Open a new terminal, or run this to use Tyrion right away:"
            say ""
            say "    export PATH=\"$bin_dir:\$PATH\""
            say ""
            ;;
    esac

    say "Get started:"
    say "    tyrion                    launch the app (it will ask for an API key the first time)"
    say "    tyrion \"explain this repo\"  run a single prompt"
    say ""
    say "${DIM}Update: run this installer again    Uninstall: uv tool uninstall $PACKAGE${RESET}"
    say ""
}

# Everything above only defines functions. Nothing runs until this last line, so a
# download that is cut off part-way can never execute half of the script.
main "$@"
