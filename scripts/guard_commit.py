"""Block personal data and secrets from reaching git.

  python scripts/guard_commit.py          # check staged changes (pre-commit hook)
  python scripts/guard_commit.py --all    # check every tracked file (CI)
"""
import re, subprocess, sys

BLOCKED_PATHS = re.compile(r"(^|/)(data/|\.env$|auth\.json$|.*\.pem$|.*_raw\.json$|optins\.json$)")
SECRETS = {
    "OpenAI key": re.compile(r"sk-(proj-)?[A-Za-z0-9_-]{20,}"),
    "GitHub token": re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
    "AWS key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "URL token": re.compile(r"[?&](token|tk|key|api_key)=[A-Za-z0-9_-]{6,}"),
    "Bearer token": re.compile(r"Bearer [A-Za-z0-9._-]{24,}"),
}
MAX_BYTES = 2_000_000


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout


def main():
    every = "--all" in sys.argv
    files = git("ls-files").split("\n") if every else git("diff", "--cached", "--name-only", "--diff-filter=ACM").split("\n")
    problems = []
    for f in filter(None, files):
        if f == "scripts/guard_commit.py":
            continue
        if BLOCKED_PATHS.search(f):
            problems.append(f"{f}: personal data / secrets path")
            continue
        blob = git("show", f":{f}") if not every else open(f, encoding="utf-8", errors="replace").read()
        if len(blob.encode("utf-8", "replace")) > MAX_BYTES:
            problems.append(f"{f}: larger than {MAX_BYTES // 1_000_000} MB (scraped data?)")
        for name, rx in SECRETS.items():
            m = rx.search(blob)
            if m:
                problems.append(f"{f}: looks like a {name} ({m.group(0)[:12]}...)")
    if problems:
        print("guard_commit: blocked\n  " + "\n  ".join(problems))
        print("Remove it, or if it is a false positive, adjust scripts/guard_commit.py in its own reviewed PR.")
        sys.exit(1)


if __name__ == "__main__":
    main()
