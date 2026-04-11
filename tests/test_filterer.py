"""Tests for filterer module."""
from datetime import datetime, timezone

from filterer import deduplicate, exclude_noise


def test_deduplicate_empty():
    """Test deduplicate with empty list."""
    assert deduplicate([]) == []


def test_deduplicate_no_duplicates():
    """Test deduplicate when there are no duplicates."""
    items = [
        {"id": "a", "published": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)},
        {"id": "b", "published": datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)},
        {"id": "c", "published": datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)},
    ]
    result = deduplicate(items)
    assert len(result) == 3
    assert [item["id"] for item in result] == ["a", "b", "c"]


def test_deduplicate_keeps_newest():
    """Test that deduplicate keeps the newest item when duplicates exist."""
    items = [
        {"id": "a", "published": datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc), "source": "old"},
        {"id": "a", "published": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc), "source": "new"},
        {"id": "b", "published": datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)},
    ]
    result = deduplicate(items)
    assert len(result) == 2

    # Find the item with id "a" and verify it's the newer one
    item_a = next(item for item in result if item["id"] == "a")
    assert item_a["source"] == "new"


def test_deduplicate_preserves_order_by_date():
    """Test that results are sorted by published date (newest first)."""
    items = [
        {"id": "c", "published": datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)},
        {"id": "a", "published": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)},
        {"id": "b", "published": datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)},
    ]
    result = deduplicate(items)
    assert [item["id"] for item in result] == ["a", "b", "c"]


def test_deduplicate_multiple_duplicates():
    """Test with multiple duplicate groups."""
    items = [
        {"id": "a", "published": datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)},
        {"id": "a", "published": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)},
        {"id": "a", "published": datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)},
        {"id": "b", "published": datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc)},
        {"id": "b", "published": datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc)},
    ]
    result = deduplicate(items)
    assert len(result) == 2
    assert [item["id"] for item in result] == ["b", "a"]


def test_exclude_noise_filters_sponsored_titles_and_links():
    items = [
        {"title": "Sponsored webinar: build agents", "link": "https://example.com/news/1"},
        {"title": "Real story", "link": "https://example.com/spons/paid-post"},
        {"title": "Actual update", "link": "https://example.com/news/2"},
    ]

    result, skipped = exclude_noise(items)
    assert skipped == 2
    assert result == [{"title": "Actual update", "link": "https://example.com/news/2"}]


def test_exclude_noise_filters_openai_academy_items():
    items = [
        {
            "source": "OpenAI News",
            "title": "Working with files in ChatGPT",
            "link": "https://openai.com/academy/working-with-files",
        },
        {
            "source": "OpenAI News",
            "title": "OpenAI launches enterprise controls",
            "link": "https://openai.com/index/openai-launches-enterprise-controls",
        },
    ]

    result, skipped = exclude_noise(items)
    assert skipped == 1
    assert result == [items[1]]


def test_exclude_noise_filters_techcrunch_event_promos():
    items = [
        {
            "source": "TechCrunch",
            "title": "TechCrunch is heading to Tokyo — and bringing the Startup Battlefield with it",
            "link": "https://techcrunch.com/example-1",
        },
        {
            "source": "TechCrunch",
            "title": "Last 24 hours: Save up to $500 on your TechCrunch Disrupt 2026 pass",
            "link": "https://techcrunch.com/example-2",
        },
        {
            "source": "TechCrunch",
            "title": "Anthropic rolls out a new enterprise plan",
            "link": "https://techcrunch.com/example-3",
        },
    ]

    result, skipped = exclude_noise(items)
    assert skipped == 2
    assert result == [items[2]]


def test_exclude_noise_filters_the_verge_podcasts_and_discussion_posts():
    items = [
        {
            "source": "The Verge",
            "title": "Fear and loathing at OpenAI",
            "link": "https://www.theverge.com/podcast/909621/openai-sam-altman-drama-vergecast",
        },
        {
            "source": "The Verge",
            "title": "The Vergecast: AI drama keeps escalating",
            "link": "https://www.theverge.com/podcast/909999/vergecast-ai-drama",
        },
        {
            "source": "The Verge",
            "title": "Microsoft starts removing Copilot buttons from Windows 11 apps",
            "link": "https://www.theverge.com/news/909640/microsoft-removing-copilot-windows-11-buttons",
        },
    ]

    result, skipped = exclude_noise(items)
    assert skipped == 2
    assert result == [items[2]]


def test_exclude_noise_keeps_legit_verge_news_under_podcast_path():
    items = [
        {
            "source": "The Verge",
            "title": "AI startup launches agent benchmark",
            "link": "https://www.theverge.com/podcast/123/ai-startup-launches-agent-benchmark",
        },
    ]

    result, skipped = exclude_noise(items)
    assert skipped == 0
    assert result == items


def test_exclude_noise_filters_non_ai_simon_willison_posts():
    items = [
        {
            "source": "Simon Willison",
            "title": "Kākāpō parrots",
            "link": "https://simonwillison.net/2026/Apr/9/kakapo-parrots/",
        },
        {
            "source": "Simon Willison",
            "title": "GitHub Repo Size",
            "link": "https://simonwillison.net/2026/Apr/9/github-repo-size/",
        },
        {
            "source": "Simon Willison",
            "title": "ChatGPT voice mode is a weaker model",
            "link": "https://simonwillison.net/2026/Apr/9/chatgpt-voice-mode/",
        },
    ]

    result, skipped = exclude_noise(items)
    assert skipped == 2
    assert result == [items[2]]


def test_exclude_noise_filters_ai_human_interest_and_crime_titles():
    items = [
        {
            "source": "Wired AI",
            "title": "Suspect Arrested for Allegedly Throwing Molotov Cocktail at Sam Altman's Home",
            "link": "https://www.wired.com/story/example-1",
        },
        {
            "source": "Wired AI",
            "title": "AI Podcasters Really Want to Tell You How to Keep a Man Happy",
            "link": "https://www.wired.com/story/example-2",
        },
        {
            "source": "Ars Technica",
            "title": "The Pro-Iran Meme Machine Trolling Trump With AI Lego Cartoons",
            "link": "https://arstechnica.com/example-3",
        },
        {
            "source": "The Verge",
            "title": "The Iranian Lego AI video creators credit their virality to 'heart'",
            "link": "https://www.theverge.com/example-3b",
        },
        {
            "source": "Wired AI",
            "title": "OpenAI Backs Bill That Would Limit Liability for AI-Enabled Mass Deaths or Financial Disasters",
            "link": "https://www.wired.com/story/example-4",
        },
    ]

    result, skipped = exclude_noise(items)
    assert skipped == 4
    assert result == [items[4]]


def test_exclude_noise_keeps_legit_lego_and_gen_z_ai_stories():
    items = [
        {
            "source": "Ars Technica",
            "title": "Lego uses generative AI to design new sets for 2026",
            "link": "https://example.com/lego",
        },
        {
            "source": "The Verge",
            "title": "Gen Z workers are bringing ChatGPT into the enterprise",
            "link": "https://example.com/genz",
        },
    ]

    result, skipped = exclude_noise(items)
    assert skipped == 0
    assert result == items


def test_exclude_noise_filters_wired_editorial_framing_and_advice():
    items = [
        {
            "source": "Wired AI",
            "title": "Anthropic’s Mythos Will Force a Cybersecurity Reckoning—Just Not the One You Think",
            "link": "https://www.wired.com/story/example-1",
        },
        {
            "source": "Wired AI",
            "title": "This Startup Wants You to Pay Up to Talk With AI Versions of Human Experts",
            "link": "https://www.wired.com/story/example-2",
        },
        {
            "source": "Wired AI",
            "title": "Meta’s New AI Asked for My Raw Health Data—and Gave Me Terrible Advice",
            "link": "https://www.wired.com/story/example-3",
        },
        {
            "source": "Wired AI",
            "title": "OpenAI Backs Bill That Would Limit Liability for AI-Enabled Mass Deaths or Financial Disasters",
            "link": "https://www.wired.com/story/example-4",
        },
    ]

    result, skipped = exclude_noise(items)
    assert skipped == 3
    assert result == [items[3]]


def test_exclude_noise_filters_apple_updates_posts():
    items = [
        {
            "source": "Apple Machine Learning Research",
            "title": "ACM Human-Computer Interaction Conference (CHI) 2026",
            "link": "https://machinelearning.apple.com/updates/apple-at-chi-2026",
        },
        {
            "source": "Apple Machine Learning Research",
            "title": "LaCy: What Small Language Models Can and Should Learn is Not Just a Question of Loss",
            "link": "https://machinelearning.apple.com/research/lacy",
        },
    ]

    result, skipped = exclude_noise(items)
    assert skipped == 1
    assert result == [items[1]]


def test_exclude_noise_keeps_broader_ai_model_posts_from_simon():
    items = [
        {
            "source": "Simon Willison",
            "title": "Qwen 3 is surprisingly good",
            "link": "https://example.com/qwen",
        },
        {
            "source": "Simon Willison",
            "title": "DeepSeek-R2 and local inference notes",
            "link": "https://example.com/deepseek",
        },
        {
            "source": "Simon Willison",
            "title": "Gemma 3 on a Mac mini",
            "link": "https://example.com/gemma",
        },
        {
            "source": "Simon Willison",
            "title": "Claude 4 system prompts",
            "link": "https://example.com/claude",
        },
    ]

    result, skipped = exclude_noise(items)
    assert skipped == 0
    assert result == items
