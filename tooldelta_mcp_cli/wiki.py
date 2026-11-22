"""Search and read the Markdown distributed with the CLI."""

import re
from functools import cache
from importlib import resources


ID_PREFIX = "bundled-wiki/"


def _markdown(directory, prefix=""):
    for path in directory.iterdir():
        if path.name.startswith("."):
            continue
        relative = prefix + path.name
        if path.is_dir():
            yield from _markdown(path, relative + "/")
        elif relative.endswith(".md") and path.is_file():
            yield relative, path


@cache
def _pages():
    root = resources.files(__package__).joinpath("_wiki", "docs")
    if not root.is_dir():
        return {}
    pages = {}
    for relative, path in sorted(_markdown(root)):
        text = path.read_text(encoding="utf-8-sig")
        heading = re.search(r"^#{1,6}[ \t]+(.+)$", text, re.MULTILINE)
        title = heading[1].strip() if heading else path.name[:-3]
        if relative == "index.md" and not heading:
            title = "ToolDelta Wiki"
        pages[ID_PREFIX + relative] = (title, text, text.casefold())
    return pages


def available():
    return bool(_pages())


def rank(item, terms):
    heading = (item["id"] + " " + item["title"]).casefold()
    return sum(term in heading for term in terms)


def search(terms, limit):
    hits = []
    for id, (title, text, body) in _pages().items():
        heading = (id + " " + title).casefold()
        if not all(term in heading or term in body for term in terms):
            continue
        index = max(0, body.find(terms[0]) - 35) if terms else 0
        hits.append({"id": id, "title": title, "excerpt": text[index:index + 180]})
    hits.sort(key=lambda hit: rank(hit, terms), reverse=True)
    return {"total": len(hits), "items": hits[:limit]}


def get(id, offset=0, limit=8000):
    title, text, _ = _pages()[id]
    end = min(len(text), offset + limit)
    return {
        "id": id, "title": title, "text": text[offset:end], "total_chars": len(text),
        "next_offset": end if end < len(text) else None,
    }
