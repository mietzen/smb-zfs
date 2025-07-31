import re
import os
import sys
import getpass
from typing import Dict, Callable, Any

from .const import CONFIRM_PHRASE
from .errors import SmbZfsError


def password_check(password: str) -> Dict[str, bool]:
    """Verifies the strength of a password against a set of criteria."""
    length_error = len(password) < 8
    digit_error = re.search(r"\d", password) is None
    uppercase_error = re.search(r"[A-Z]", password) is None
    lowercase_error = re.search(r"[a-z]", password) is None
    symbol_error = re.search(r"\W", password) is None
    password_ok = not (
        length_error or digit_error or uppercase_error or lowercase_error or symbol_error)

    return {
        'password_ok': password_ok,
        'length_error': length_error,
        'digit_error': digit_error,
        'uppercase_error': uppercase_error,
        'lowercase_error': lowercase_error,
        'symbol_error': symbol_error,
    }


def prompt_for_password(username: str) -> str:
    """Securely prompts for a password, checks its strength, and confirms it."""
    while True:
        password = getpass.getpass(f"Enter password for user '{username}': ")
        if not password:
            print("Password cannot be empty.")
            continue

        check = password_check(password)
        if not check['password_ok']:
            print("Password is not strong enough:")
            if check['length_error']:
                print("- It must be at least 8 characters long.")
            if check['digit_error']:
                print("- It must contain at least one digit.")
            if check['uppercase_error']:
                print("- It must contain at least one uppercase letter.",
                      file=sys.stderr)
            if check['lowercase_error']:
                print("- It must contain at least one lowercase letter.",
                      file=sys.stderr)
            if check['symbol_error']:
                print("- It must contain at least one symbol.")
            continue

        password_confirm = getpass.getpass("Confirm password: ")
        if password == password_confirm:
            return password
        print("Passwords do not match. Please try again.")


def confirm_destructive_action(prompt: str, yes_flag: bool) -> bool:
    """Asks for confirmation for a destructive action unless a 'yes' flag is provided."""
    if yes_flag:
        return True
    print(f"WARNING: {prompt}")
    print(
        f"To proceed, type the following phrase exactly: {CONFIRM_PHRASE}",
    )
    response = input("> ")
    return response == CONFIRM_PHRASE


def handle_exception(func: Callable[..., Any]) -> Callable[..., Any]:
    """A decorator to catch and print SmbZfsError exceptions, then exit."""
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except SmbZfsError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    return wrapper


def check_root() -> None:
    """Checks if the script is being run by the root user."""
    if os.geteuid() != 0:
        raise SmbZfsError("This script must be run as root.")
