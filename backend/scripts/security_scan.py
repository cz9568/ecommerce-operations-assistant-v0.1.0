import re
import sys

from backend.app.config import PROJECT_ROOT

EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "release",
    "reports",
    "storage",
    "__pycache__",
}
TEXT_SUFFIXES = {
    ".html",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".toml",
    ".ts",
    ".vue",
    ".yaml",
    ".yml",
}
PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "alibaba-access-key": re.compile(r"\bLTAI[A-Za-z0-9]{12,}\b"),
    "openai-style-key": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}


def main() -> int:
    findings: list[str] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file() or path.name == ".env":
            continue
        if any(part in EXCLUDED_PARTS for part in path.parts) or path.suffix not in TEXT_SUFFIXES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            for name, pattern in PATTERNS.items():
                if pattern.search(line):
                    relative = path.relative_to(PROJECT_ROOT)
                    findings.append(f"{relative}:{line_number}: {name}")
    if findings:
        print("Potential committed secret material found:")
        print("\n".join(findings))
        return 1
    print("Secret-pattern scan passed (local .env and runtime directories excluded).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
