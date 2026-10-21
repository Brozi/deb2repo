import sys


def prompt_user(message: str) -> str:
    """Prompt the user for input, enssuring the prompt text is written to stderr."""
    sys.stderr.write(message)
    sys.stderr.flush()

    return input().strip()


def confirm_action(message: str) -> bool:
    """Helper for Yes/No prompts."""
    choice = prompt_user(f"{message} [Y/n]: ").lower()
    return choice in ("", "y", "yes")


def print_success(human_message: str, script_data: str) -> None:
    """
    Intelligently routes output based on whether user is in a terminal
    or piping the output to a script.
    """
    if sys.stdout.isatty():
        print(human_message)
    else:
        print(human_message, file=sys.stderr)
        print(script_data)
