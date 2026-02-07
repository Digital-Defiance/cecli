import re


def preprocess_json(response: str) -> str:
    response = fix_json_backslashes(response)
    return response


def fix_json_backslashes(raw_str: str) -> str:
    """
    Finds invalid JSON escape sequences and escapes the backslash
    so it is treated as a literal character.
    """
    # Look for a backslash NOT followed by valid escape characters
    # We use a capturing group for the backslash to replace it
    invalid_escape_pattern = r'\\(?!(["\\\/bfnrt]|u[0-9a-fA-F]{4}))'

    # Replace the single backslash with a double backslash
    return re.sub(invalid_escape_pattern, r"\\\\", raw_str)
