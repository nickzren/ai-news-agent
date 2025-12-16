"""Tests for graph module - fallback categorization."""
from graph import _fallback_categorize


def test_fallback_categorize_papers_source():
    """Test that items from Papers source get Research & Models."""
    item = {"title": "Some headline", "source": "Hugging Face Papers"}
    assert _fallback_categorize(item) == "Research & Models"


def test_fallback_categorize_policy_keywords():
    """Test policy/ethics keyword detection."""
    items = [
        {"title": "New AI lawsuit filed against company", "source": "TechCrunch"},
        {"title": "AI copyright issues in court", "source": "Wired"},
        {"title": "AI safety concerns raised", "source": "MIT"},
        {"title": "New AI regulation proposed", "source": "Guardian"},
    ]
    for item in items:
        assert _fallback_categorize(item) == "Policy & Ethics"


def test_fallback_categorize_research_keywords():
    """Test research keyword detection."""
    items = [
        {"title": "New paper on transformers", "source": "ArXiv"},
        {"title": "Research shows AI improvement", "source": "MIT"},
        {"title": "New model beats benchmark", "source": "Google"},
        {"title": "Arxiv paper released", "source": "Unknown"},
    ]
    for item in items:
        assert _fallback_categorize(item) == "Research & Models"


def test_fallback_categorize_tools_keywords():
    """Test tools/applications keyword detection."""
    items = [
        {"title": "Company launches new AI tool", "source": "TechCrunch"},
        {"title": "New API release from OpenAI", "source": "OpenAI"},
        {"title": "Feature update for ChatGPT", "source": "The Verge"},
    ]
    for item in items:
        assert _fallback_categorize(item) == "Tools & Applications"


def test_fallback_categorize_business_keywords():
    """Test business/industry keyword detection."""
    items = [
        {"title": "AI startup raises $50M", "source": "TechCrunch"},
        {"title": "Company funding round announced", "source": "VentureBeat"},
        {"title": "$100 billion valuation", "source": "WSJ"},
    ]
    for item in items:
        assert _fallback_categorize(item) == "Industry & Business"


def test_fallback_categorize_tutorials_keywords():
    """Test tutorials/insights keyword detection."""
    items = [
        {"title": "How to use ChatGPT effectively", "source": "Medium"},
        {"title": "Complete guide to LLMs", "source": "Blog"},
        {"title": "Tutorial on fine-tuning", "source": "HuggingFace"},
        {"title": "Why AI matters for developers", "source": "Dev.to"},
    ]
    for item in items:
        assert _fallback_categorize(item) == "Tutorials & Insights"


def test_fallback_categorize_breaking_keywords():
    """Test breaking news keyword detection."""
    items = [
        {"title": "OpenAI announces GPT-5", "source": "OpenAI"},
        {"title": "Google unveils new Gemini", "source": "Google"},
    ]
    for item in items:
        assert _fallback_categorize(item) == "Breaking News"


def test_fallback_categorize_default():
    """Test that unmatched items get default category."""
    item = {"title": "Some random AI headline", "source": "Unknown"}
    # Should return the default category (Industry & Business)
    result = _fallback_categorize(item)
    assert result == "Industry & Business"


def test_fallback_categorize_case_insensitive():
    """Test that keyword matching is case insensitive."""
    item = {"title": "NEW LAWSUIT FILED", "source": "News"}
    assert _fallback_categorize(item) == "Policy & Ethics"

    item = {"title": "COMPANY RAISES FUNDING", "source": "News"}
    assert _fallback_categorize(item) == "Industry & Business"
