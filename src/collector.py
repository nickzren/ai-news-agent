import feedparser, hashlib, json, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_DAY = timedelta(days=1)

# Location of feeds configuration file (project root)
_FEEDS_FILE = Path(__file__).resolve().parent.parent / "feeds.json"

try:
    FEEDS = json.loads(_FEEDS_FILE.read_text())
except (FileNotFoundError, json.JSONDecodeError):
    FEEDS = {}

def _now():
    return datetime.now(timezone.utc)

def _parse_date(entry):
    for attr in ("published_parsed", "updated_parsed"):
        tup = entry.get(attr)
        if tup:
            return datetime.fromtimestamp(time.mktime(tup), tz=timezone.utc)
    return None

def collect_items():
    """Return list[dict] fresh within 24 h."""
    cutoff = _now() - _DAY
    items = []
    for url, meta in FEEDS.items():
        category = meta["category"]
        src = meta["source"]
        try:
            parsed = feedparser.parse(url)
        except Exception as exc:  # feedparser can raise on bad feeds
            print(f"⚠️  feed error for {url}: {exc}")
            continue
        # src = parsed.feed.get("title", url)  # Removed per instructions
        for e in parsed.entries:
            ts = _parse_date(e)
            if not ts or ts < cutoff:
                continue
            title, link = e.get("title", "").strip(), e.get("link", "").strip()
            if not (title and link):
                continue
            uid = hashlib.sha1(link.encode()).hexdigest()
            items.append(
                {
                    "id": uid,
                    "title": title,
                    "link": link,
                    "source": src,
                    "published": ts,
                    "category": category,
                }
            )
    return items