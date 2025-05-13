from collections import defaultdict

def to_markdown(items):
    if not items:
        return "_No fresh AI headlines in the last 24 h._"

    sections = defaultdict(list)
    for it in items:
        cat = it.get("category", "Other")
        sections[cat].append(it)

    lines = ["## Daily AI / LLM Headlines\n"]
    for cat in sorted(sections):
        lines.append(f"### {cat}")
        for i in sections[cat]:
            title = i["title"].strip()
            if "blurb" in i:       # added later by the LLM agent
                title += f" — *{i['blurb']}*"
            lines.append(f"- [{title}]({i['link']}) — {i['source']}")
        lines.append("")           # blank line
    return "\n".join(lines)