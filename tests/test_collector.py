"""Tests for collector module - URL normalization."""
from collector import normalize_url


def test_normalize_url_basic():
    """Test basic URL normalization."""
    url = "https://example.com/article"
    assert normalize_url(url) == "https://example.com/article"


def test_normalize_url_removes_trailing_slash():
    """Test that trailing slashes are removed."""
    url = "https://example.com/article/"
    assert normalize_url(url) == "https://example.com/article"


def test_normalize_url_preserves_root_slash():
    """Test that root path slash is preserved."""
    url = "https://example.com/"
    assert normalize_url(url) == "https://example.com/"


def test_normalize_url_removes_www():
    """Test that www. prefix is removed."""
    url = "https://www.example.com/article"
    assert normalize_url(url) == "https://example.com/article"


def test_normalize_url_lowercases_host():
    """Test that hostname is lowercased."""
    url = "https://EXAMPLE.COM/Article"
    result = normalize_url(url)
    assert "example.com" in result


def test_normalize_url_removes_utm_params():
    """Test that UTM tracking parameters are removed."""
    url = "https://example.com/article?utm_source=twitter&utm_medium=social"
    assert normalize_url(url) == "https://example.com/article"


def test_normalize_url_removes_various_tracking_params():
    """Test that various tracking parameters are removed."""
    url = "https://example.com/article?fbclid=abc123&ref=homepage&gclid=xyz"
    assert normalize_url(url) == "https://example.com/article"


def test_normalize_url_preserves_meaningful_params():
    """Test that non-tracking query parameters are preserved."""
    url = "https://example.com/search?q=test&page=2"
    result = normalize_url(url)
    assert "q=" in result or "page=" in result


def test_normalize_url_mixed_params():
    """Test URL with both tracking and meaningful params."""
    url = "https://example.com/article?id=123&utm_source=twitter"
    result = normalize_url(url)
    assert "id=" in result
    assert "utm_source" not in result


def test_normalize_url_different_schemes():
    """Test that http URLs work too."""
    url = "http://example.com/article"
    assert normalize_url(url) == "http://example.com/article"


def test_normalize_url_complex():
    """Test complex URL normalization."""
    url = "HTTPS://WWW.Example.COM/Path/To/Article/?utm_source=test&id=123&utm_medium=email"
    result = normalize_url(url)
    assert "https://example.com/Path/To/Article" in result
    assert "id=123" in result
    assert "utm_source" not in result
    assert "utm_medium" not in result
