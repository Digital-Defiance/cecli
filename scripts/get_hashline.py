import os
import sys
from pathlib import Path

# Add the current directory to sys.path to allow importing from cecli
sys.path.append(os.getcwd())

from cecli.helpers.hashline import hashline  # noqa


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/get_hashline.py <file_path>")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"Error: File '{file_path}' not found.")
        sys.exit(1)

    try:
        content = file_path.read_text(encoding="utf-8")
        hashed_content = hashline(content)
        print(hashed_content, end="")
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
