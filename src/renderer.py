from collections import defaultdict

def to_markdown(items):
    if not items:
        return "_No fresh AI headlines in the last 24 h._"

    sections = defaultdict(list)
    for it in items:
        cat = it.get("category", "Other")
        sections[cat].append(it)

    lines = ["## Daily AI / LLM Headlines\n"]
    
    # Define category order for AI news
    category_order = [
        "Breaking News",
        "Industry & Business",
        "Tools & Applications",
        "Research & Models",
        "Policy & Ethics",
        "Tutorials & Insights",
        "Other"
    ]
    
    for cat in category_order:
        if cat not in sections:
            continue
        lines.append(f"### {cat}")
        
        # Sort items: first by source (alphabetically), then by date (newest first)
        sorted_items = sorted(sections[cat], 
                            key=lambda x: (x['source'], -x['published'].timestamp()))
        
        for i in sorted_items:
            title = i["title"].strip()
            lines.append(f"- [{title}]({i['link']}) — {i['source']}")
        lines.append("")  # blank line
        
    return "\n".join(lines)