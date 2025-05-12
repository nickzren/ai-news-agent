from collections import defaultdict

CATEGORIES = {
    "MIT Technology Review": "News & Mags",
    "Wired":                 "News & Mags",
    "Ars Technica":          "News & Mags",
    "TechCrunch":            "News & Mags",
    "VentureBeat":           "News & Mags",
    "OpenAI":                "Lab Blogs",
    "Google AI Blog":        "Lab Blogs",
    "DeepMind":              "Lab Blogs",
    "Anthropic":             "Lab Blogs",
    "Hugging Face":          "Lab Blogs",
    "Ben's Bites":           "Newsletters",
    "Import AI":             "Newsletters",
    "Papers with Code":      "Research",
    "arXiv.org":             "Research",
}

def to_markdown(items):
    if not items:
        return "_No fresh AI headlines in the last 24 h._"

    sections = defaultdict(list)

    for it in items:
        src = it["source"]
        cat = "Other"
        for key, group in CATEGORIES.items():
            if key.lower() in src.lower():
                cat = group
                break
        sections[cat].append(it)

    lines = ["## Daily AI Headlines\n"]
    for cat in sorted(sections):
        lines.append(f"### {cat}")
        for i in sections[cat]:
            title = i["title"].strip()
            if "blurb" in i:       # added later by the LLM agent
                title += f" — *{i['blurb']}*"
            lines.append(f"- [{title}]({i['link']}) — {i['source']}")
        lines.append("")           # blank line
    return "\n".join(lines)