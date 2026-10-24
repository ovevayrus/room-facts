"""Bright Data API key: BRIGHTDATA_API_KEY, else the token in the Bright Data MCP URL in ~/.claude.json."""
import json, os, pathlib
from urllib.parse import urlparse, parse_qs


def bd_key():
    if os.getenv("BRIGHTDATA_API_KEY"):
        return os.environ["BRIGHTDATA_API_KEY"]

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)
        elif isinstance(node, str) and "mcp.brightdata.com" in node and "token=" in node:
            yield parse_qs(urlparse(node).query)["token"][0]

    cfg = json.loads((pathlib.Path.home() / ".claude.json").read_text(encoding="utf-8"))
    for token in walk(cfg):
        return token
    raise SystemExit("No Bright Data key: set BRIGHTDATA_API_KEY")
