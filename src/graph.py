"""
LangGraph pipeline for ai-news-agent

Flow:
    collect ─▶ filter ─▶ shortify ─▶ categorize ─▶ render
"""
from __future__ import annotations

import os
from openai import OpenAI
from pathlib import Path
from typing import TypedDict, List, Dict
from collections import defaultdict

from dotenv import load_dotenv
from langgraph.graph import StateGraph

from collector import collect_items
from filterer import deduplicate
from renderer import to_markdown

# load .env once
load_dotenv()

# ──────────────────────────────────────────────────────────────
# 1. Shared state definition
class DigestState(TypedDict, total=False):
    items:    List[Dict]   # list of headline dicts
    markdown: str          # final rendered MD


# ──────────────────────────────────────────────────────────────
# 2. Nodes
def node_collect(state: DigestState) -> DigestState:
    items = collect_items()
    print(f"📊 Collected {len(items)} items")
    state["items"] = items
    return state


def node_filter(state: DigestState) -> DigestState:
    items = deduplicate(state.get("items", []))
    
    # Limit papers to avoid overwhelming the digest
    paper_count = 0
    filtered_items = []
    skipped_papers = 0
    
    for item in sorted(items, key=lambda x: x["published"], reverse=True):
        if "Papers" in item.get("source", "") and paper_count >= 7:
            print(f"   Skipping paper: {item['title'][:50]}...")
            skipped_papers += 1
            continue  # Skip additional papers
        if "Papers" in item.get("source", ""):
            paper_count += 1
        filtered_items.append(item)
    
    print(f"📊 After deduplication: {len(items)} items")
    if skipped_papers > 0:
        print(f"📊 Skipped {skipped_papers} additional papers (kept top 7)")
    print(f"📊 After limiting papers: {len(filtered_items)} items")
    state["items"] = filtered_items
    return state


def node_shortify(state: DigestState) -> DigestState:
    """
    Shorten titles to ≤10 words for cleaner digest and better duplicate detection
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠️  No OPENAI_API_KEY found, skipping shortify")
        return state

    if not state.get("items"):
        print("⚠️  No items to shortify")
        return state

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)

    shortified_count = 0
    for item in state["items"]:
        prompt = (
            "Rewrite this headline in ≤10 words, keep the core idea:\n"
            f"{item['title']}"
        )
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            item["title"] = resp.choices[0].message.content.strip()
            shortified_count += 1
        except Exception as exc:
            print(f"⚠️  LLM error for item {shortified_count + 1}: {exc}")
            
    print(f"📊 Shortified {shortified_count}/{len(state.get('items', []))} items")
    return state


def node_categorize(state: DigestState) -> DigestState:
    """
    Use LLM to categorize items and identify duplicates.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    
    # If no API key, set default categories
    if not api_key:
        print("⚠️  No OPENAI_API_KEY found, using default categorization")
        categories = [
            "Breaking News",
            "Industry & Business",
            "Tools & Applications",
            "Research & Models",
            "Policy & Ethics",
            "Tutorials & Insights"
        ]
        for i, item in enumerate(state.get("items", [])):
            item["category"] = categories[i % len(categories)]
        return state
        
    if not state.get("items"):
        print("⚠️  No items to categorize")
        return state
    
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    try:
        client = OpenAI(api_key=api_key)
        
        # Create item list with shortened titles
        items_text = "\n".join([
            f"{i+1}. {item['title']} — {item['source']}"
            for i, item in enumerate(state["items"])
        ])
        
        prompt = f"""Analyze these AI news headlines for duplicates and categorization.

CRITICAL DUPLICATE DETECTION:
Look for stories about the SAME EVENT even if worded differently:
- "OpenAI launches X" = "X released by OpenAI" = "New X from OpenAI"
- "Google announces Y" = "Y unveiled by Google" = "Google's new Y"
- "Model Z beats benchmark" = "Z achieves state-of-art" = "New record by Z"
- "Company raises $X" = "X funding for Company" = "Company valued at Y"
- Same paper/research from different sources

Mark ALL BUT ONE as SKIP for each duplicate group. Keep the most informative version.

CATEGORIES:
- Breaking News: Major AI models, breakthroughs, or announcements TODAY
- Industry & Business: Funding, acquisitions, company news, valuations
- Tools & Applications: New tools, APIs, product launches, features
- Research & Models: Papers, research findings, benchmarks, model releases
- Policy & Ethics: Legal, copyright, safety, regulation, lawsuits
- Tutorials & Insights: How-to guides, opinions, analysis, thought pieces

Items:
{items_text}

For each item, respond with ONLY:
- The category name (if keeping)
- SKIP (if duplicate)

One per line. Be VERY aggressive marking duplicates."""

        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        
        # Parse categorization response
        response_text = resp.choices[0].message.content.strip()
        print(f"📊 LLM categorization response received")
        
        lines = [line.strip() for line in response_text.split('\n') if line.strip()]
        
        # Valid categories
        valid_categories = [
            "Breaking News",
            "Industry & Business",
            "Tools & Applications",
            "Research & Models",
            "Policy & Ethics",
            "Tutorials & Insights"
        ]
        
        # First pass: LLM categorization
        for i, line in enumerate(lines):
            if i >= len(state["items"]):
                break
            
            # Check for SKIP
            if "SKIP" in line.upper():
                state["items"][i]["skip"] = True
                state["items"][i]["skip_reason"] = "duplicate"
                continue
            
            # Check for exact category match
            category_found = False
            for valid_cat in valid_categories:
                if valid_cat.lower() in line.lower():
                    state["items"][i]["category"] = valid_cat
                    category_found = True
                    break
            
            # If no match found, use default based on keywords
            if not category_found:
                title = state["items"][i]["title"].lower()
                source = state["items"][i]["source"].lower()
                
                # Source-based categorization first
                if "papers" in source:
                    state["items"][i]["category"] = "Research & Models"
                # Keyword-based categorization
                elif any(word in title for word in ["lawsuit", "court", "legal", "copyright", "safety"]):
                    state["items"][i]["category"] = "Policy & Ethics"
                elif any(word in title for word in ["paper", "research", "model", "benchmark", "beats"]):
                    state["items"][i]["category"] = "Research & Models"
                elif any(word in title for word in ["launch", "release", "tool", "api", "feature"]):
                    state["items"][i]["category"] = "Tools & Applications"
                elif any(word in title for word in ["raise", "funding", "$", "acquire", "valuation"]):
                    state["items"][i]["category"] = "Industry & Business"
                elif any(word in title for word in ["how", "guide", "tutorial", "should", "opinion"]):
                    state["items"][i]["category"] = "Tutorials & Insights"
                else:
                    state["items"][i]["category"] = "Industry & Business"
                    
                print(f"⚠️  Used fallback categorization for: {state['items'][i]['title']}")
        
        # Second pass: Additional duplicate detection based on key terms
        seen_topics = {}
        for i, item in enumerate(state["items"]):
            if item.get("skip"):
                continue
                
            title_lower = item["title"].lower()
            
            # Extract company/product names for duplicate detection
            companies = ["openai", "google", "microsoft", "meta", "anthropic", "amazon"]
            for company in companies:
                if company in title_lower:
                    # Create a topic key without common words
                    key_words = [w for w in title_lower.split() 
                               if len(w) > 3 and w not in ["with", "from", "announces", "launches"]]
                    topic_key = f"{company}_{'_'.join(sorted(key_words[:3]))}"
                    
                    if topic_key in seen_topics:
                        item["skip"] = True
                        item["skip_reason"] = f"duplicate topic"
                        print(f"📊 Additional duplicate found: {item['title']}")
                    else:
                        seen_topics[topic_key] = i
                    break
                    
        # Remove skipped items
        original_count = len(state["items"])
        state["items"] = [item for item in state["items"] if not item.get("skip")]
        
        print(f"📊 After categorization: {len(state['items'])} items (skipped {original_count - len(state['items'])} duplicates)")
        
        # Debug: show categories assigned
        cats = defaultdict(int)
        for item in state["items"]:
            cats[item.get("category", "Unknown")] += 1
        print(f"📊 Category distribution: {dict(cats)}")
        
    except Exception as exc:
        print(f"⚠️  Categorization error: {exc}")
        import traceback
        traceback.print_exc()
        
        # Set default varied categories on error
        categories = ["Industry & Business", "Research & Models", "Tools & Applications"]
        for i, item in enumerate(state.get("items", [])):
            item["category"] = categories[i % len(categories)]
    
    return state


def node_render(state: DigestState) -> DigestState:
    items = state.get("items", [])
    print(f"📊 Rendering {len(items)} items")
    markdown = to_markdown(items)
    Path("news.md").write_text(markdown, encoding="utf-8")
    state["markdown"] = markdown
    return state


# ──────────────────────────────────────────────────────────────
# 3. Build LangGraph
def build_graph():
    g = StateGraph(DigestState)

    g.add_node("collect", node_collect)
    g.add_node("filter", node_filter)
    g.add_node("shortify", node_shortify)
    g.add_node("categorize", node_categorize)
    g.add_node("render", node_render)

    g.set_entry_point("collect")
    g.add_edge("collect", "filter")
    g.add_edge("filter", "shortify")
    g.add_edge("shortify", "categorize")
    g.add_edge("categorize", "render")

    return g.compile()