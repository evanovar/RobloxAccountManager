"""
UI Helper functions
Color codes and console utilities
"""

import msvcrt


class Colors:
    """ANSI color codes for console output"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    RESET = '\033[0m'


def colored_text(text, color):
    """Return colored text for console output"""
    return f"{color}{text}{Colors.RESET}"


def get_password_with_asterisks(prompt="Enter password: "):
    """Get password input with asterisk masking (Windows-specific)"""
    print(prompt, end='', flush=True)
    password = ""
    while True:
        char = msvcrt.getch()
        if char in (b'\r', b'\n'):
            print()
            break
        elif char == b'\x08':
            if len(password) > 0:
                password = password[:-1]
                print('\b \b', end='', flush=True)
        elif char == b'\x03':
            raise KeyboardInterrupt
        else:
            password += char.decode('utf-8', errors='ignore')
            print('*', end='', flush=True)
    return password
