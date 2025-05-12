import feedparser, hashlib, time
from datetime import datetime, timedelta, timezone

_DAY = timedelta(days=1)

FEEDS = [
    # News & Magazines
    "https://www.technologyreview.com/topic/artificial-intelligence/feed/",
    "https://www.wired.com/feed/tag/ai/latest/rss",
    "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "https://techcrunch.com/tag/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
    # Lab & Research blogs
    "https://openai.com/feed.xml",
    "https://ai.googleblog.com/atom.xml",
    "https://www.deepmind.com/feeds/blog.xml",
    "https://www.anthropic.com/news-feed.xml",
    "https://huggingface.co/blog/rss.xml",
    # Newsletters / Aggregators
    "https://bensbites.beehiiv.com/feed",
    "https://jackclark.net/feed.xml",
    # Research
    "https://paperswithcode.com/rss",
    "https://arxiv.org/rss/cs.CL",
]

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
    for url in FEEDS:
        parsed = feedparser.parse(url)
        src = parsed.feed.get("title", url)
        for e in parsed.entries:
            ts = _parse_date(e)
            if not ts or ts < cutoff:
                continue
            title, link = e.get("title", "").strip(), e.get("link", "").strip()
            if not (title and link):
                continue
            uid = hashlib.sha1(link.encode()).hexdigest()
            items.append(
                {"id": uid, "title": title, "link": link, "source": src, "published": ts}
            )
    return items