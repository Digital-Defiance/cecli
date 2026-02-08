import re


def preprocess_json(response: str) -> str:
    # This pattern matches any sequence of backslashes followed by
    # a character or a unicode sequence.
    pattern = r'(\\+)(u[0-9a-fA-F]{4}|["\\\/bfnrt]|.)?'

    def normalize(match):
        suffix = match.group(2) or ""

        # If it's a valid escape character (like \n or \u0020)
        # we ensure it has exactly ONE backslash.
        if re.match(r'^(u[0-9a-fA-F]{4}|["\\\/bfnrt])$', suffix):
            return "\\" + suffix

        # Otherwise, it's a literal backslash (like C:\temp)
        # We ensure it is escaped for JSON (exactly TWO backslashes).
        return "\\\\" + suffix

    return re.sub(pattern, normalize, response)
