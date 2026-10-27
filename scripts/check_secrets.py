"""C1-7, GH-10: refuse a file that holds a secret value. Run: python scripts/check_secrets.py <folder> [<folder> ...].

Give the Solution folder and the folder of the copied Precord, so a credential in either one fails the check."""
import re
import sys
from pathlib import Path

PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    # A quoted value, with a quoted or a bare key: `password = "..."`, `"password": "..."`, `DB_PASSWORD="..."`.
    # A value that starts with `$`, `<` or `{` is a placeholder.
    re.compile(r"(?i)(?:password|passwd|secret|token|api_key|apikey)[\"']?\s*[:=]\s*[\"'][^\s\"'$<{][^\s\"']{7,}[\"']"),
)
# In a settings file a value has no quotes: `password: x` in YAML, `DB_PASSWORD=x` in an env file.
# In code the same form is a call or a name, so this pattern reads settings files only.
SETTING = re.compile(r"(?i)^\s*(?:export\s+)?[\w.-]*(?:password|passwd|secret|token|api_key|apikey)\s*[:=]\s*"
                     r"[^\s\"'$<{#][^\s#]{7,}\s*$")
SETTING_SUFFIXES = {".env", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".properties"}
# A settings value that names itself a stand-in, such as `ci-config-check-only`, is not a secret.
PLACEHOLDER = re.compile(r"(?i)check-only|placeholder|example|changeme|change-me|dummy|not-a-secret")
SKIP = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache"}
THIS_SCRIPT = Path(__file__).resolve()


def is_settings(path: Path) -> bool:
    return path.suffix in SETTING_SUFFIXES or path.name.startswith(".env")


def scan(root: Path) -> list[str]:
    found = []
    for path in sorted(root.rglob("*")):
        # Skip by the path inside the scan root, so a root under such a folder is still read.
        if not path.is_file() or SKIP & set(path.relative_to(root).parts) or path.suffix in {".tgz", ".png", ".ico"}:
            continue
        if path.resolve() == THIS_SCRIPT:
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        settings = is_settings(path)
        for number, line in enumerate(text.splitlines(), 1):
            if any(pattern.search(line) for pattern in PATTERNS) or (
                    settings and SETTING.search(line) and not PLACEHOLDER.search(line)):
                found.append(f"{path.relative_to(root)}:{number}")
    return found


if __name__ == "__main__":
    folders = [Path(name) for name in sys.argv[1:]] or [Path(".")]
    hits = [f"{folder}/{hit}" for folder in folders for hit in scan(folder)]
    for hit in hits:
        print(f"Secret value in {hit}")
    raise SystemExit(1 if hits else 0)
