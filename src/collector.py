import feedparser, hashlib, time
from datetime import datetime, timedelta, timezone

_DAY = timedelta(days=1)

FEEDS = {
    # Lab & Research blogs
    "https://openai.com/news/rss.xml": {
        "category": "Lab Blogs",
        "source": "OpenAI"
    },
    "https://blog.google/technology/ai/rss/": {
        "category": "Lab Blogs",
        "source": "Google"
    },
    "https://huggingface.co/blog/feed.xml": {
        "category": "Lab Blogs",
        "source": "Hugging Face"
    },

    # News & Magazines
    "https://www.technologyreview.com/topic/artificial-intelligence/feed/": {
        "category": "News & Mags",
        "source": "MIT Technology Review"
    },
    "https://www.wired.com/feed/tag/ai/latest/rss": {
        "category": "News & Mags",
        "source": "Wired"
    },
    "https://feeds.arstechnica.com/arstechnica/technology-lab": {
        "category": "News & Mags",
        "source": "Ars Technica"
    },
    "https://techcrunch.com/tag/artificial-intelligence/feed/": {
        "category": "News & Mags",
        "source": "TechCrunch"
    },
    "https://venturebeat.com/category/ai/feed/": {
        "category": "News & Mags",
        "source": "VentureBeat"
    },

    # Newsletters / Aggregators
    "https://thesequence.substack.com/feed": {
        "category": "Newsletters",
        "source": "The Sequence"
    },
    "https://importai.substack.com/feed": {
        "category": "Newsletters",
        "source": "Import AI"
    },
    "https://www.latent.space/feed.xml": {
        "category": "Newsletters",
        "source": "Latent Space"
    },
    "https://aibreakfast.substack.com/feed": {
        "category": "Newsletters",
        "source": "AI Breakfast"
    },

    # Research
    "https://arxiv.org/rss/cs.CL": {
        "category": "Research",
        "source": "arXiv"
    },
    "https://jamesg.blog/hf-papers.xml": {
        "category": "Research",
        "source": "Hugging Face Papers"
    },
}

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