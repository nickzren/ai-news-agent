# src/graph.py
"""
LangGraph pipeline for ai-news-agent

Flow:
    collect ─▶ filter ─▶ shortify ─▶ render
"""
from __future__ import annotations

import os
from openai import OpenAI
from pathlib import Path
from typing import TypedDict, List, Dict

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
    state["items"] = collect_items()
    return state


def node_filter(state: DigestState) -> DigestState:
    state["items"] = deduplicate(state.get("items", []))
    return state


def node_shortify(state: DigestState) -> DigestState:
    """
    Rewrite each item's title in ≤10 words using an LLM.
    Skips silently if no OPENAI_API_KEY is set.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # running in free mode – nothing to do
        return state

    model = os.getenv("OPENAI_MODEL")

    # Create OpenAI client (uses env vars if api_key is None)
    client = OpenAI(api_key=api_key) if api_key else None

    for item in state["items"]:
        prompt = (
            "Rewrite this headline in ≤10 words, keep the core idea:\n"
            f"{item['title']}"
        )
        try:
            if client:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=32,
                    temperature=0.3,
                )
                item["title"] = resp.choices[0].message.content.strip()
        except Exception as exc:
            # fail gracefully – just log & continue
            print("⚠️  LLM error:", exc)
    return state


def node_render(state: DigestState) -> DigestState:
    markdown = to_markdown(state.get("items", []))
    Path("news.md").write_text(markdown, encoding="utf-8")
    state["markdown"] = markdown
    return state


# ──────────────────────────────────────────────────────────────
# 3. Build LangGraph
def build_graph():
    g = StateGraph(DigestState)

    g.add_node("collect", node_collect)
    g.add_node("filter",  node_filter)
    g.add_node("shortify",   node_shortify)
    g.add_node("render",  node_render)

    g.set_entry_point("collect")
    g.add_edge("collect", "filter")
    g.add_edge("filter",  "shortify")
    g.add_edge("shortify",   "render")

    return g.compile()