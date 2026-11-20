#!/usr/bin/env python3
"""Today board: show the level-2 headings under "* Today" in an org file on an old Kindle browser.

Stdlib only. Run it on the Mac that has the notes file:

    python3 server.py

Configuration is environment only, because none of it changes at runtime:

    TODAY_NOTES_FILE   org file to read, at each request  (default ~/org/notes.org)
    TODAY_HOST         bind address                       (default 0.0.0.0, so the LAN can reach it)
    TODAY_PORT         bind port                          (default 8788)
"""

import os
import re
import sys
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

NOTES_FILE = os.environ.get("TODAY_NOTES_FILE", "~/org/notes.org")
HOST = os.environ.get("TODAY_HOST", "0.0.0.0")
PORT = int(os.environ.get("TODAY_PORT", "8788"))

REFRESH_SECONDS = 300
MAX_ITEMS = 12
MAX_CHARS = 80  # the whole text, including the "…" that marks a cut

HEADING = re.compile(r"^(\*+)[ \t]+(.*?)[ \t]*$")
TAGS = re.compile(r"[ \t]+:(?:[\w@#%]+:)+$")
KEYWORD = re.compile(r"^(?:TODO|DONE|NEXT|WAITING|WAIT|CANCELLED|CANCELED)(?:[ \t]+|$)")
PRIORITY = re.compile(r"^\[#(?:[A-Z]|\d+)\](?:[ \t]+|$)")
LINK = re.compile(r"\[\[([^\]]*)\](?:\[([^\]]*)\])?\]")


def clean_heading(title):
    """Reduce an org heading (tags already removed) to the plain text the page shows."""
    title = PRIORITY.sub("", KEYWORD.sub("", title.strip()), count=1)
    title = LINK.sub(lambda m: m.group(2) or m.group(1), title).strip()
    if len(title) > MAX_CHARS:
        title = title[: MAX_CHARS - 1].rstrip() + "…"
    return title


def parse_today(text):
    """Return the cleaned level-2 headings of the first "* Today" section, in file order.

    The section ends at the next level-1 heading. Level 3 and deeper, and body text, are ignored.
    """
    items, in_today = [], False
    for line in text.splitlines():
        match = HEADING.match(line)
        if not match:
            continue
        level, title = len(match.group(1)), TAGS.sub("", match.group(2))
        if level == 1:
            if in_today:
                break
            in_today = title == "Today"
        elif level == 2 and in_today:
            title = clean_heading(title)
            if title:
                items.append(title)
    return items


def load_today(path):
    """Read the notes file now. A missing or unreadable file gives an empty list, never an error."""
    try:
        with open(os.path.expanduser(path), encoding="utf-8", errors="replace") as notes:
            return parse_today(notes.read())
    except FileNotFoundError:  # the normal "no list yet" case; the start-up line shows the path
        return []
    except OSError as error:
        print(f"notes read failed: {error}", file=sys.stderr)
        return []


STYLE = """
* { margin: 0; padding: 0; }
body { width: 800px; height: 600px; background: #fff; color: #000;
       font-family: sans-serif; -webkit-text-size-adjust: none; }
table { width: 800px; table-layout: fixed; border-collapse: collapse; }
/* One line per row, clipped at the page edge: 12 rows then always fit in 600px. */
td { padding: 4px 20px; font-size: 26px; line-height: 1.2; border-bottom: 2px solid #000;
     white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.more { font-weight: bold; }
.foot { padding: 6px 20px; font-size: 17px; }
.msg { padding: 60px 20px; font-size: 32px; font-weight: bold; }
"""

# The Kindle variant of the page: same markup, plus the scale and portrait
# orientation that the Kindle browser needs. Same values as ink-dashboard.
KINDLE_STYLE = (
    "html{overflow:hidden}body{-webkit-transform:scale(0.75);-webkit-transform-origin:0 0;}"
)
KINDLE_SCRIPT = (
    '<script type="text/javascript">'
    'try{kindle.dev.setOrientation("portrait");}catch(e){}</script>'
)


def _page(body, kindle=False):
    return (
        "<!DOCTYPE html>\n<html><head>"
        '<meta http-equiv="Content-Type" content="text/html; charset=utf-8">'
        f'<meta http-equiv="refresh" content="{REFRESH_SECONDS}">'
        "<title>Today</title>"
        f"<style>{STYLE}{KINDLE_STYLE if kindle else ''}</style>"
        f"{KINDLE_SCRIPT if kindle else ''}"
        f"</head><body>{body}</body></html>\n"
    )


def render(items, now=None, kindle=False):
    now = now or datetime.now()
    if items:
        rows = [f"<tr><td>{escape(item)}</td></tr>" for item in items[:MAX_ITEMS]]
        if len(items) > MAX_ITEMS:
            rows.append(f'<tr><td class="more">+{len(items) - MAX_ITEMS} more</td></tr>')
        body = f"<table>{''.join(rows)}</table>"
    else:
        body = '<div class="msg">No Today list</div>'
    return _page(body + f'<div class="foot">Updated {now.strftime("%H:%M")}</div>', kindle)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path, _, query = self.path.partition("?")
        if path not in ("/", "/index.html"):
            self.send_error(404)
            return
        # ?k=1 asks for the Kindle variant.
        body = render(load_today(NOTES_FILE), kindle="k" in parse_qs(query)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"today-board on http://{HOST}:{PORT}/ reading {NOTES_FILE}")
    HTTPServer((HOST, PORT), Handler).serve_forever()
