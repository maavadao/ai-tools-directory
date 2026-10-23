"""Polite fetching of public web pages: obeys robots.txt, identifies itself, caps size and speed."""
from __future__ import annotations

import time
import urllib.error
import urllib.request
import urllib.robotparser
from urllib.parse import urlparse

USER_AGENT = "maavadao-ai-tools-directory (+https://maavadao.com/ai-tools; contact via github.com/maavadao)"
MAX_BYTES = 1_500_000
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_last_hit: dict[str, float] = {}


def allowed(url: str) -> bool:
    """False if the site's robots.txt asks bots (or us) to stay away from this URL."""
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            req = urllib.request.Request(f"{base}/robots.txt", headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=15) as resp:
                rp.parse(resp.read(200_000).decode("utf-8", "replace").splitlines())
            _robots[base] = rp
        except urllib.error.HTTPError as exc:
            # 4xx means no robots.txt, so everything is allowed; 5xx we treat as "stay away".
            _robots[base] = None if exc.code < 500 else rp
            if exc.code >= 500:
                rp.disallow_all = True
        except Exception:  # noqa: BLE001 - unreachable site: let fetch() fail on its own
            _robots[base] = None
    rp = _robots[base]
    return rp is None or rp.can_fetch(USER_AGENT, url)


def fetch(url: str, delay: float = 1.0) -> tuple[str, str] | None:
    """(final URL, text) of an HTML page, or None if disallowed, missing or not HTML."""
    if not allowed(url):
        return None
    host = urlparse(url).netloc
    wait = _last_hit.get(host, 0) + delay - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.5"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            if "html" not in resp.headers.get("Content-Type", "html"):
                return None
            raw = resp.read(MAX_BYTES)
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.geturl(), raw.decode(charset, "replace")
    except Exception:  # noqa: BLE001 - any failure just means "no data this time"
        return None
