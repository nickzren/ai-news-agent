# AI News Agent

[![Daily AI News Digest](https://github.com/nickzren/ai-news-agent/actions/workflows/digest.yml/badge.svg)](https://github.com/nickzren/ai-news-agent/actions/workflows/digest.yml)
[![Read latest digests](https://img.shields.io/badge/Read-latest%20digests-181717?logo=github&logoColor=white)](https://github.com/nickzren/ai-news-agent/issues?q=label%3Aai-digest)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A short daily digest of AI news, delivered to your inbox. Headlines are collected from ~25 trusted sources (TechCrunch, Wired, Ars Technica, The Verge, OpenAI, Anthropic, and more), deduplicated, grouped by topic, and posted as a GitHub Issue every day.

## Get the daily digest

🔔 **[Watch this repository](https://github.com/nickzren/ai-news-agent/subscription)** with notifications set to **Issues**. GitHub will email you each new digest. A GitHub account is required for email notifications; no separate newsletter service.

[**→ Browse all digests**](https://github.com/nickzren/ai-news-agent/issues?q=label%3Aai-digest)

## What it looks like

Top stories from **May 13, 2026**:

- **[Anthropic Leads Ramp Business Data](https://techcrunch.com/2026/05/13/anthropic-now-has-more-business-customers-than-openai-according-to-ramp-data/)** — TechCrunch
- **[WhatsApp Adds Private AI Chats](https://www.wired.com/story/whatsapp-incognito-chat-meta-ai/)** — Wired AI
- **[ChatGPT Drug Advice Lawsuit Filed](https://arstechnica.com/tech-policy/2026/05/will-i-be-ok-teen-died-after-chatgpt-pushed-deadly-mix-of-drugs-lawsuit-says/)** — Ars Technica

*[Browse latest digests →](https://github.com/nickzren/ai-news-agent/issues?q=label%3Aai-digest)*

## How it works

Every morning, an automated workflow reads the RSS feeds listed in [`feeds.json`](feeds.json), removes duplicates, groups related stories, and asks an LLM to pick the most important ones. The result is posted as a single, skimmable GitHub Issue.

## For developers

- [docs/development.md](docs/development.md) — setup, agent-driven mode, feed configuration
- [docs/architecture.md](docs/architecture.md) — pipeline diagrams and design notes
- [AGENTS.md](AGENTS.md) — runbook for Codex / Claude Code automation

## License

[MIT](LICENSE)
