"""
RSS feed collector for ai-news-agent
"""
import hashlib
import json
import logging
import socket
import time
from urllib.error import URLError
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

import feedparser
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import RSS_TIMEOUT, RSS_RETRIES, RSS_USER_AGENT

logger = logging.getLogger(__name__)

_DAY = timedelta(days=1)

# Location of feeds configuration file (project root)
_FEEDS_FILE = Path(__file__).resolve().parent.parent / "feeds.json"

try:
    FEEDS = json.loads(_FEEDS_FILE.read_text())
    logger.info(f"Loaded {len(FEEDS)} feeds from feeds.json")
except (FileNotFoundError, json.JSONDecodeError) as e:
    logger.error(f"Error loading feeds.json: {e}")
    FEEDS = {}


def _now():
    return datetime.now(timezone.utc)


def _parse_date(entry):
    for attr in ("published_parsed", "updated_parsed"):
        tup = entry.get(attr)
        if tup:
            return datetime.fromtimestamp(time.mktime(tup), tz=timezone.utc)
    return None


def normalize_url(url: str) -> str:
    """
    Normalize URL to improve duplicate detection.
    - Lowercase scheme and host
    - Remove trailing slashes
    - Remove common tracking parameters
    - Remove www. prefix
    """
    parsed = urlparse(url)

    # Lowercase scheme and netloc
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Remove www. prefix
    if netloc.startswith("www."):
        netloc = netloc[4:]

    # Remove trailing slash from path
    path = parsed.path.rstrip("/") if parsed.path != "/" else parsed.path

    # Remove common tracking parameters
    tracking_params = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "ref", "source", "fbclid", "gclid", "mc_cid", "mc_eid",
    }

    if parsed.query:
        query_params = parse_qs(parsed.query, keep_blank_values=True)
        filtered_params = {
            k: v for k, v in query_params.items()
            if k.lower() not in tracking_params
        }
        query = urlencode(filtered_params, doseq=True) if filtered_params else ""
    else:
        query = ""

    return urlunparse((scheme, netloc, path, "", query, ""))


def _log_retry(retry_state) -> None:  # type: ignore[no-untyped-def]
    """Log retry attempts."""
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(f"Fetch attempt {retry_state.attempt_number} failed, retrying: {exc}")


@retry(
    stop=stop_after_attempt(RSS_RETRIES + 1),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((URLError, socket.timeout, TimeoutError)),
    before_sleep=_log_retry,
)
def _fetch_with_retry(url: str) -> feedparser.FeedParserDict:
    """Fetch RSS feed with retry logic and proper headers."""
    # Set global timeout for socket operations
    old_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(RSS_TIMEOUT)
        parsed = feedparser.parse(
            url,
            request_headers={"User-Agent": RSS_USER_AGENT},
        )
        # feedparser doesn't raise on HTTP errors, check bozo flag
        if parsed.bozo and isinstance(parsed.bozo_exception, Exception):
            exc = parsed.bozo_exception
            # Re-raise connection/timeout errors to trigger retry
            if isinstance(exc, (URLError, socket.timeout, TimeoutError)):
                raise exc
        return parsed
    finally:
        socket.setdefaulttimeout(old_timeout)


def collect_items():
    """Return list[dict] fresh within 24 h."""
    cutoff = _now() - _DAY
    logger.info(f"Collecting items newer than {cutoff}")
    items = []

    for url, meta in FEEDS.items():
        category = meta["category"]
        src = meta["source"]
        try:
            logger.info(f"Fetching {src}...")
            parsed = _fetch_with_retry(url)

            if parsed.bozo:
                logger.warning(f"Parse error for {src}: {parsed.bozo_exception}")
                continue

            entries_count = len(parsed.entries) if hasattr(parsed, 'entries') else 0
            logger.debug(f"Found {entries_count} entries from {src}")

        except Exception as exc:
            logger.error(f"Feed error for {url}: {exc}")
            continue

        for e in parsed.entries:
            ts = _parse_date(e)
            if not ts:
                continue

            if ts < cutoff:
                continue

            title, link = e.get("title", "").strip(), e.get("link", "").strip()
            if not (title and link):
                continue

            # Normalize URL before hashing
            normalized_link = normalize_url(link)
            uid = hashlib.sha1(normalized_link.encode()).hexdigest()

            items.append(
                {
                    "id": uid,
                    "title": title,
                    "link": link,  # Keep original link for display
                    "source": src,
                    "published": ts,
                    "category": category,
                }
            )

    logger.info(f"Collected {len(items)} total items from all feeds")
    return items
