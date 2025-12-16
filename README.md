# ai-news-agent

[![Daily AI News Digest](https://github.com/nickzren/ai-news-agent/actions/workflows/digest.yml/badge.svg)](https://github.com/nickzren/ai-news-agent/actions/workflows/digest.yml)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Powered-FF6B6B)](https://github.com/langchain-ai/langgraph)
[![OpenAI](https://img.shields.io/badge/GPT--5-mini-412991?logo=openai&logoColor=white)](https://openai.com/)
[![RSS](https://img.shields.io/badge/RSS-Feeds-FFA500?logo=rss&logoColor=white)](feeds.json)
[![GitHub Issues](https://img.shields.io/badge/Output-GitHub%20Issues-181717?logo=github&logoColor=white)](https://github.com/nickzren/ai-news-agent/issues?q=label%3Aai-digest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A lightweight AI agent that grabs fresh AI-related headlines and posts a daily digest to GitHub Issues.

🔔 **Watch this repository** to receive the daily AI news digest email delivered straight to your inbox.

## Prerequisites

- Python 3.12+ with pip

## Quick Start

### 1. Install UV

```bash
pip install uv
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### 3. Run
```bash
uv run python src/main.py
```

## Feed configuration

The collector reads RSS feed URLs from [`feeds.json`](feeds.json) in the project root. The
file should contain a JSON object where each key is a feed URL and each value
specifies the `category` and human‑readable `source` name.
