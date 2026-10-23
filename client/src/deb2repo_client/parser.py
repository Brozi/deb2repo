import argparse


def build_add_parser(subparsers: argparse._SubParsersAction) -> None:
    """Configures the 'add' subcommand"""
    parser = subparsers.add_parser(
        "add", help="Add a new repo to the tracking database"
    )
    parser.add_argument("url", help="Repository URL")
    parser.add_argument("-d", "--distro", required=True, help="Target distribution")
    parser.add_argument(
        "-p",
        "--package",
        help="Explicitly name the package to track. None tracks all.",
    )


def build_remove_parser(subparsers: argparse._SubParsersAction) -> None:
    """Congigures the 'remove' subcommand"""
    parser = subparsers.add_parser(
        "remove", help="Remove the repo from tracking and delete associated files"
    )
    parser.add_argument(
        "name", help="Repository name to sync (e.g., 'bat', or 'sharkdp/bat')."
    )
    parser.add_argument(
        "-d",
        "--distro",
        help="Disambiguate when the same repo is tracked for multiple distros.",
    )
    parser.add_argument(
        "-H",
        "--host",
        help="Disambiguate when the same repo is tracked from multiple hosts (e.g., github.com, gitlab.com).",
    )
    parser.add_argument(
        "--no-confirm",
        "-n",
        action="store_true",
        help="Disable interactive prompts, and auto-accept partial matches. Use with caution.",
    )


def build_list_parser(subparsers: argparse._SubParsersAction) -> None:
    """Configures the 'list' subcommand"""
    parser = subparsers.add_parser("list", help="List tracked repos")
    parser.add_argument("-d", "--distro", help="Filter the list by the chosen distro")


def build_sync_parser(subparsers: argparse._SubParsersAction) -> None:
    """Configures the 'sync' subcommand"""
    parser = subparsers.add_parser(
        "sync", help="Trigger a polling cycle for a given repo, or all repos by default"
    )
    parser.add_argument(
        "name",
        nargs="?",
        help="Repository name to sync (e.g., 'bat', or 'sharkdp/bat'). Omit to sync all.",
    )
    parser.add_argument(
        "-d",
        "--distro",
        help="Disambiguate when the same repo is tracked for multiple distros.",
    )
    parser.add_argument(
        "-H",
        "--host",
        help="Disambiguate when the same repo is tracked from multiple hosts (e.g., github.com, gitlab.com).",
    )
    parser.add_argument(
        "--no-confirm",
        "-n",
        action="store_true",
        help="Disable interactive prompts, and auto-accept partial matches. Use with caution.",
    )


def build_import_parser(subparsers: argparse._SubParsersAction) -> None:
    """Configures the 'import' subcommand"""
    parser = subparsers.add_parser(
        "import", help="Bulk import repositories from a text file"
    )
    parser.add_argument("file", help="Path to the text file containing repository URLs")
    parser.add_argument(
        "-d",
        "--distro",
        required=True,
        help="Target distribution for all imported repositories.",
    )


def build_tui_parser(subparsers: argparse._SubParsersAction) -> None:
    """Configures the 'tui' subcommand"""
    subparsers.add_parser("tui", help="Launch the text-based user interface")


def build_master_parser() -> argparse.ArgumentParser:
    """Builds the root argument parser and attaches all commands"""
    parser = argparse.ArgumentParser(
        description="Deb2repo CLI client for interacting with the APT repo."
    )
    parser.add_argument(
        "-s",
        "--scripting",
        action="store_true",
        help="Output in a scripting-friendly format",
    )

    subparsers = parser.add_subparsers(dest="command")

    build_add_parser(subparsers)
    build_remove_parser(subparsers)
    build_list_parser(subparsers)
    build_sync_parser(subparsers)
    build_import_parser(subparsers)
    build_tui_parser(subparsers)

    return parser
