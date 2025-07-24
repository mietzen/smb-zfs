import re
import getpass

def password_check(password):
    """
    Verify the strength of 'password'
    Returns a dict indicating the wrong criteria
    A password is considered strong if:
        8 characters length or more
        1 digit or more
        1 symbol or more
        1 uppercase letter or more
        1 lowercase letter or more
    """

    # calculating the length
    length_error = len(password) < 8

    # searching for digits
    digit_error = re.search(r"\d", password) is None

    # searching for uppercase
    uppercase_error = re.search(r"[A-Z]", password) is None

    # searching for lowercase
    lowercase_error = re.search(r"[a-z]", password) is None

    # searching for symbols
    symbol_error = re.search(r"\W", password) is None

    # overall result
    password_ok = not ( length_error or digit_error or uppercase_error or lowercase_error or symbol_error )

    return {
        'password_ok' : password_ok,
        'length_error' : length_error,
        'digit_error' : digit_error,
        'uppercase_error' : uppercase_error,
        'lowercase_error' : lowercase_error,
        'symbol_error' : symbol_error,
    }


def prompt_for_password(username):
    """Securely prompts for a password, checks strength, and confirms."""
    while True:
        password = getpass.getpass(f"Enter password for user '{username}': ")
        if not password:
            print("Password cannot be empty.", file=sys.stderr)
            continue

        check = password_check(password)
        if not check['password_ok']:
            print("Password is not strong enough:", file=sys.stderr)
            if check['length_error']:
                print("- It must be at least 8 characters long.", file=sys.stderr)
            if check['digit_error']:
                print("- It must contain at least one digit.", file=sys.stderr)
            if check['uppercase_error']:
                print("- It must contain at least one uppercase letter.", file=sys.stderr)
            if check['lowercase_error']:
                print("- It must contain at least one lowercase letter.", file=sys.stderr)
            if check['symbol_error']:
                print("- It must contain at least one symbol.", file=sys.stderr)
            continue

        password_confirm = getpass.getpass("Confirm password: ")
        if password == password_confirm:
            return password
        print("Passwords do not match. Please try again.", file=sys.stderr)
