# ai-news-agent

A lightweight AI agent that grabs fresh AI-related headlines and posts a daily digest to GitHub Issues.

🔔 **Watch this repository** to receive the daily AI news digest email delivered straight to your inbox.

## Quick start (local)

```bash
mamba env create -f environment.yml
conda activate ai-news-agent
export PYTHONPATH=src
python src/main.py
```

## Feed configuration

The collector reads RSS feed URLs from `feeds.json` in the project root. The
file should contain a JSON object where each key is a feed URL and each value
specifies the `category` and human‑readable `source` name.

Example:

```json
{
  "https://openai.com/news/rss.xml": {
    "category": "Lab Blogs",
    "source": "OpenAI"
  }
}
```

Feeds defined in this file are used by the collector. If the file is missing or
invalid, no feeds will be loaded.
