# today-board

A tiny web page that shows your org-mode "Today" list on an old Kindle browser.

It reads `* Today` in an org file at each request and lists its level-2 headings (`** ...`) in file order. It shows the first 12, then "+N more". It removes TODO keywords, priority cookies, and tags, and it turns org links into their description. It cuts each line to 80 characters. If the file or `* Today` is missing, the page says "No Today list". The page reloads itself every 300 seconds.

Python 3, standard library only.

## Run

    python3 server.py

Open `http://localhost:8788/`.

## Kindle

Find the IP address of the computer that runs the server. On the Kindle, open `http://<mac-ip>:8788/?k=1`. The `?k=1` page uses the scale and portrait mode that the Kindle browser needs.

## Settings

Set these as environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `TODAY_NOTES_FILE` | `~/org/notes.org` | The org file to read |
| `TODAY_HOST` | `0.0.0.0` | Bind address (`0.0.0.0` lets the LAN reach it) |
| `TODAY_PORT` | `8788` | Bind port |

The page has no login. Run it only on a network that you trust.

## Test

    python3 -m unittest -v

## License

MIT
