#!/usr/bin/env python3
"""Self-check for the board's real logic: the Today section parser, the page, and the handler.

Run with: python3 -m unittest -v
"""

import io
import os
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from unittest import mock

import server
from server import MAX_CHARS, MAX_ITEMS, REFRESH_SECONDS, load_today, parse_today, render

NOW = datetime(2026, 11, 20, 19, 30)


def notes(*lines):
    return "\n".join(lines) + "\n"


class ParseToday(unittest.TestCase):
    def test_section_boundary(self):
        text = notes(
            "* Inbox",
            "** before",
            "* Today",
            "Some body text.",
            "** first",
            "*** deeper, ignored",
            "**** deeper still, ignored",
            "Body under first.",
            "** second",
            "* Later",
            "** after",
        )
        self.assertEqual(parse_today(text), ["first", "second"])

    def test_today_with_tags(self):
        self.assertEqual(parse_today(notes("* Today  :work:home:", "** a")), ["a"])

    def test_today_must_be_level_one_and_exact(self):
        self.assertEqual(parse_today(notes("** Today", "** a")), [])
        self.assertEqual(parse_today(notes("* Today list", "** a")), [])
        self.assertEqual(parse_today(notes("*Today", "** a")), [])

    def test_only_first_today_section(self):
        self.assertEqual(parse_today(notes("* Today", "** a", "* Today", "** b")), ["a"])

    def test_no_today_or_empty_today(self):
        self.assertEqual(parse_today(""), [])
        self.assertEqual(parse_today(notes("* Inbox", "** a")), [])
        self.assertEqual(parse_today(notes("* Today", "body only", "*** deep", "* Next")), [])

    def test_links(self):
        text = notes(
            "* Today",
            "** Read [[https://example.com/a][the article]] now",
            "** Open [[https://example.com/b]]",
            "** [[a][one]] and [[b][two]] and [[https://c.example]]",
        )
        self.assertEqual(
            parse_today(text),
            ["Read the article now", "Open https://example.com/b", "one and two and https://c.example"],
        )

    def test_link_description_with_brackets(self):
        text = notes("* Today", "** [[id:book][Chapter [draft] now]] :x:", "** [[a][b [c]]] then [[d][e]]")
        self.assertEqual(parse_today(text), ["Chapter [draft] now", "b [c] then e"])

    def test_tags(self):
        text = notes("* Today", "** Call Sam :phone:", "** Plan :a:b@c:", "** a:b: not tags")
        self.assertEqual(parse_today(text), ["Call Sam", "Plan", "a:b: not tags"])

    def test_tag_only_heading_is_skipped(self):
        # Org gives these an empty title: they must not show their tags or use one of the 12 slots.
        text = notes("* Today", "** :work:", "** TODO :work:home:", "** [#A] :x:", "** real")
        self.assertEqual(parse_today(text), ["real"])

    def test_keywords_and_priority(self):
        text = notes(
            "* Today",
            "** TODO buy milk",
            "** DONE ship it",
            "** NEXT call",
            "** WAIT reply",
            "** WAITING reply 2",
            "** CANCELLED old",
            "** CANCELED old 2",
            "** TODO [#A] urgent :x:",
            "** [#B] only priority",
            "** TODOLIST is not a keyword",
            "** TODO",
            "** todo lowercase stays",
        )
        self.assertEqual(
            parse_today(text),
            [
                "buy milk",
                "ship it",
                "call",
                "reply",
                "reply 2",
                "old",
                "old 2",
                "urgent",
                "only priority",
                "TODOLIST is not a keyword",
                "todo lowercase stays",
            ],
        )

    def test_cut_to_80(self):
        text = notes("* Today", "** " + "x" * 80, "** " + "y" * 81, "** TODO " + "z" * 200)
        exact, cut, cut_keyword = parse_today(text)
        self.assertEqual(exact, "x" * 80)
        for item in (cut, cut_keyword):
            self.assertEqual(len(item), MAX_CHARS)
            self.assertTrue(item.endswith("…"))
        self.assertEqual(cut, "y" * 79 + "…")
        self.assertEqual(cut_keyword, "z" * 79 + "…")

    def test_cut_counts_link_description_not_url(self):
        text = notes("* Today", "** [[https://example.com/" + "u" * 200 + "][short]]")
        self.assertEqual(parse_today(text), ["short"])

    def test_unicode_separators_stay_inside_the_line(self):
        # splitlines() would cut at U+2028, U+2029, and form feed and make "** ..." a heading.
        text = notes("* Today", "** real", "Body\u2028** from U+2028", "Body\x0c** from FF", "Body\u2029** from U+2029")
        self.assertEqual(parse_today(text), ["real"])

    def test_file_order_and_crlf(self):
        self.assertEqual(parse_today("* Today\r\n** b\r\n** a\r\n** c\r\n"), ["b", "a", "c"])


class LoadToday(unittest.TestCase):
    def test_reads_temp_file_with_tilde_free_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "notes.org")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(notes("* Today", "** café ☕"))
            self.assertEqual(load_today(path), ["café ☕"])

    def test_tilde_is_expanded(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.dict(os.environ, {"HOME": folder}):
            with open(os.path.join(folder, "n.org"), "w", encoding="utf-8") as handle:
                handle.write(notes("* Today", "** home"))
            self.assertEqual(load_today("~/n.org"), ["home"])

    @mock.patch("sys.stderr", new_callable=io.StringIO)
    def test_missing_file_and_directory(self, stderr):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(load_today(os.path.join(folder, "nope.org")), [])
            self.assertEqual(load_today(folder), [])  # a directory is a read error, not a crash
        self.assertIn("notes read failed", stderr.getvalue())

    def test_invalid_utf8_does_not_crash(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "notes.org")
            with open(path, "wb") as handle:
                handle.write(b"* Today\n** bad \xff byte\n")
            self.assertEqual(len(load_today(path)), 1)


class Render(unittest.TestCase):
    def test_items_in_order(self):
        html = render(["one", "two"], NOW)
        self.assertLess(html.index("one"), html.index("two"))
        self.assertEqual(html.count("<tr>"), 2)
        self.assertIn("Updated 19:30", html)
        self.assertIn(f'http-equiv="refresh" content="{REFRESH_SECONDS}"', html)
        self.assertIn("charset=utf-8", html)
        self.assertNotIn(" more</td>", html)

    def test_limit_and_more_line(self):
        items = [f"item{i}" for i in range(MAX_ITEMS + 5)]
        html = render(items, NOW)
        self.assertIn(f"item{MAX_ITEMS - 1}<", html)
        self.assertNotIn(f"item{MAX_ITEMS}<", html)
        self.assertIn("+5 more", html)
        self.assertEqual(html.count("<tr>"), MAX_ITEMS + 1)

    def test_exactly_at_limit_has_no_more_line(self):
        html = render([f"item{i}" for i in range(MAX_ITEMS)], NOW)
        self.assertEqual(html.count("<tr>"), MAX_ITEMS)
        self.assertNotIn(" more</td>", html)

    def test_empty_shows_no_today_list(self):
        html = render([], NOW)
        self.assertIn("No Today list", html)
        self.assertNotIn("<tr>", html)
        self.assertIn("Updated 19:30", html)

    def test_escapes_heading_text(self):
        html = render(['<script>alert(1)</script> & <img src=x onerror="y">'], NOW)
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; &lt;img", html)

    def test_cut_text_is_escaped_after_the_cut(self):
        # Escaping before the cut could split an entity such as "&amp;" in half.
        [item] = parse_today(notes("* Today", "** " + "&" * 100))
        self.assertIn("&amp;" * 79 + "…", render([item], NOW))

    def test_kindle_variant(self):
        kindle = render(["a"], NOW, kindle=True)
        self.assertIn("-webkit-transform:scale(0.75)", kindle)
        self.assertIn('setOrientation("portrait")', kindle)
        plain = render(["a"], NOW)
        self.assertNotIn("-webkit-transform", plain)
        self.assertNotIn("setOrientation", plain)

    def test_old_webkit_limits(self):
        html = render(["a"], NOW)
        for banned in ("display:flex", "display: flex", "grid", "@font-face", "http://", "https://"):
            self.assertNotIn(banned, html)


class Serve(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = os.path.join(folder.name, "notes.org")
        patch = mock.patch.object(server, "NOTES_FILE", self.path)
        patch.start()
        self.addCleanup(patch.stop)
        httpd = server.make_server("127.0.0.1", 0)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        self.host, self.port = "127.0.0.1", httpd.server_port
        self.base = f"http://{self.host}:{self.port}"

    def get(self, url):
        with urllib.request.urlopen(self.base + url, timeout=5) as response:
            return response.status, response.read().decode("utf-8")

    def test_missing_file_serves_page_and_keeps_running(self):
        for _ in range(2):
            status, body = self.get("/")
            self.assertEqual(status, 200)
            self.assertIn("No Today list", body)

    def test_file_is_read_at_each_request(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(notes("* Today", "** first"))
        self.assertIn("first", self.get("/")[1])
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(notes("* Today", "** second"))
        body = self.get("/index.html")[1]
        self.assertIn("second", body)
        self.assertNotIn("first", body)

    def test_kindle_query(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(notes("* Today", "** a"))
        self.assertIn("setOrientation", self.get("/?k=1")[1])
        self.assertNotIn("setOrientation", self.get("/")[1])

    def test_idle_connection_does_not_block_other_clients(self):
        # A browser pre-connect: the socket is open and sends nothing.
        with socket.create_connection((self.host, self.port), timeout=5):
            self.assertEqual(self.get("/")[0], 200)

    def test_other_paths_are_404(self):
        for url in ("/other", "/index.htm", "/notes.org"):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.get(url)
            self.assertEqual(caught.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
