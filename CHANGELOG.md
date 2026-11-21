# Changelog

## Unreleased

- Add the Metrix.Bar dashboard `metrix/today.bar`: the Today count in the menu bar, the headings in a panel in the style of the official dashboards (refresh button, ⌘R), and small, medium, and large macOS widgets. It reads the org file directly every 60 s, so it does not need the server. A test runs its JavaScript parser in Node and compares it with `parse_today()`.
- Add the server: a LAN page of the level-2 headings under `* Today` in `~/org/notes.org`, with a `?k=1` variant for the Kindle Touch browser. Stdlib Python only; it reads the file at each request and serves clients in threads.
