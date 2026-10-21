import argparse
import sys

from deb2repo_client.cmds import cmd_add, cmd_import, cmd_list, cmd_remove, cmd_sync
from deb2repo_client.parser import build_master_parser


def execute_command(args: argparse.Namespace) -> None:
    """Routes the parsed command to the correct function."""
    commands = {
        "add": cmd_add,
        "import": cmd_import,
        "list": cmd_list,
        "remove": cmd_remove,
        "sync": cmd_sync,
    }

    if args.command not in commands:
        raise NotImplementedError(f"Command '{args.command}' is not implemented yet.")

    commands[args.command](args)


def main():

    parser = build_master_parser()

    args = parser.parse_args()

    if args.command == "tui":
        from deb2repo_client.tui import main as tui_main

        sys.exit(tui_main())

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        execute_command(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
