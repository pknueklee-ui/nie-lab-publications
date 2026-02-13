"""
NIE LAB Publication Auto-Updater (SerpAPI version)
Uses SerpAPI to fetch Google Scholar data reliably.

Usage: python update_publications.py
Requires: SERPAPI_KEY environment variable
"""

import json
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime

# ============================================
# 설정 (Configuration)
# ============================================
SCHOLAR_ID = "_ME8VaYAAAAJ"  # Google Scholar Profile ID
OUTPUT_HTML = "docs/index.html"
OUTPUT_JSON = "docs/publications.json"
MAX_PAPERS = 999

# SerpAPI key from environment variable
SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")


def serpapi_request(params):
    """Make a request to SerpAPI."""
    params["api_key"] = SERPAPI_KEY
    params["engine"] = "google_scholar_author"
    url = f"https://serpapi.com/search?{urllib.parse.urlencode(params)}"
    
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def get_author_info():
    """Get author citation stats."""
    params = {
        "author_id": SCHOLAR_ID,
        "hl": "en"
    }
    data = serpapi_request(params)
    
    cited_by = data.get("cited_by", {}).get("table", [])
    stats = {
        "total_citations": 0,
        "h_index": 0,
        "i10_index": 0
    }
    
    for row in cited_by:
        if "citations" in row:
            stats["total_citations"] = row["citations"].get("all", 0)
        elif "h_index" in row:
            stats["h_index"] = row["h_index"].get("all", 0)
        elif "i10_index" in row:
            stats["i10_index"] = row["i10_index"].get("all", 0)
    
    return stats


def get_publications(max_papers=200):
    """Get all publications from Google Scholar profile via SerpAPI."""
    all_pubs = []
    start = 0
    
    while len(all_pubs) < max_papers:
        print(f"  Fetching publications starting from {start}...")
        params = {
            "author_id": SCHOLAR_ID,
            "hl": "en",
            "start": start,
            "num": 100,
            "sort": "pubdate"
        }
        data = serpapi_request(params)
        articles = data.get("articles", [])
        
        if not articles:
            break
        
        for article in articles:
            pub = {
                "title": article.get("title", ""),
                "authors": article.get("authors", ""),
                "venue": article.get("publication", ""),
                "citations": article.get("cited_by", {}).get("value", 0),
                "year": int(article.get("year", "0")) if article.get("year", "").isdigit() else 0,
                "link": article.get("link", "#")
            }
            all_pubs.append(pub)
        
        if len(articles) < 100:
            break
        
        start += 100
        time.sleep(1)
    
    return all_pubs[:max_papers]


def generate_html(publications, stats):
    """Generate a beautiful, embeddable HTML page for publications."""
    
    # Group publications by year
    pubs_by_year = {}
    for pub in publications:
        year = pub.get("year", 0)
        year_key = str(year) if year > 0 else "Other"
        if year_key not in pubs_by_year:
            pubs_by_year[year_key] = []
        pubs_by_year[year_key].append(pub)
    
    # Sort years descending
    sorted_years = sorted(
        [y for y in pubs_by_year.keys() if y != "Other"],
        key=lambda x: int(x),
        reverse=True
    )
    if "Other" in pubs_by_year:
        sorted_years.append("Other")
    
    total_pubs = len(publications)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    
    # Build publication list HTML
    pub_sections = ""
    for year in sorted_years:
        pubs = pubs_by_year[year]
        pubs_sorted = sorted(pubs, key=lambda x: x.get("citations") or 0, reverse=True)
        
        items = ""
        for pub in pubs_sorted:
            title = pub.get("title", "Untitled")
            authors = pub.get("authors", "")
            venue = pub.get("venue", "")
            citations = pub.get("citations", 0)
            link = pub.get("link", "#")
            
            # Highlight the PI name
            authors_html = authors.replace("EK Lee", "<strong>EK Lee</strong>")
            authors_html = authors_html.replace("E Lee", "<strong>E Lee</strong>")
            authors_html = authors_html.replace("E.K. Lee", "<strong>E.K. Lee</strong>")
            
            citation_badge = ""
            if citations and citations > 0:
                badge_class = "cite-high" if citations >= 50 else ("cite-med" if citations >= 10 else "cite-low")
                citation_badge = f'<span class="cite-badge {badge_class}">{citations} citations</span>'
            
            items += f"""
            <div class="pub-item">
                <div class="pub-title"><a href="{link}" target="_blank" rel="noopener">{title}</a></div>
                <div class="pub-authors">{authors_html}</div>
                <div class="pub-venue">{venue}</div>
                {citation_badge}
            </div>"""
        
        pub_sections += f"""
        <div class="year-section">
            <div class="year-header">
                <h2>{year}</h2>
                <span class="year-count">{len(pubs)} paper{"s" if len(pubs) != 1 else ""}</span>
            </div>
            {items}
        </div>"""
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NIE LAB Publications</title>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@400;600;700&family=Noto+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}}

:root {{
    --bg: #fafaf8;
    --surface: #ffffff;
    --text-primary: #1a1a2e;
    --text-secondary: #555568;
    --text-muted: #8888a0;
    --accent: #2d5a8e;
    --accent-light: #e8f0fa;
    --border: #e8e8ee;
    --cite-high: #c0392b;
    --cite-med: #e67e22;
    --cite-low: #7f8c8d;
    --year-bg: #f0f0f5;
}}

body {{
    font-family: 'Noto Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg);
    color: var(--text-primary);
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
}}

.container {{
    max-width: 860px;
    margin: 0 auto;
    padding: 2rem 1.5rem;
}}

.stats-banner {{
    display: flex;
    gap: 1px;
    background: var(--border);
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 2rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}}

.stat-card {{
    flex: 1;
    background: var(--surface);
    padding: 1.2rem 1rem;
    text-align: center;
}}

.stat-number {{
    font-family: 'Source Serif 4', Georgia, serif;
    font-size: 1.8rem;
    font-weight: 700;
    color: var(--accent);
    line-height: 1.2;
}}

.stat-label {{
    font-size: 0.75rem;
    font-weight: 500;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 0.2rem;
}}

.year-section {{
    margin-bottom: 2rem;
}}

.year-header {{
    display: flex;
    align-items: baseline;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
    padding-bottom: 0.5rem;
    border-bottom: 2px solid var(--accent);
}}

.year-header h2 {{
    font-family: 'Source Serif 4', Georgia, serif;
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text-primary);
}}

.year-count {{
    font-size: 0.8rem;
    color: var(--text-muted);
    font-weight: 500;
}}

.pub-item {{
    padding: 1rem 0;
    border-bottom: 1px solid var(--border);
}}

.pub-item:last-child {{
    border-bottom: none;
}}

.pub-title a {{
    font-weight: 600;
    font-size: 0.95rem;
    color: var(--text-primary);
    text-decoration: none;
    line-height: 1.4;
    transition: color 0.2s;
}}

.pub-title a:hover {{
    color: var(--accent);
}}

.pub-authors {{
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin-top: 0.3rem;
}}

.pub-authors strong {{
    color: var(--accent);
    font-weight: 600;
}}

.pub-venue {{
    font-size: 0.82rem;
    color: var(--text-muted);
    font-style: italic;
    margin-top: 0.15rem;
}}

.cite-badge {{
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 0.15rem 0.5rem;
    border-radius: 10px;
    margin-top: 0.35rem;
    letter-spacing: 0.02em;
}}

.cite-high {{
    background: #fdecea;
    color: var(--cite-high);
}}

.cite-med {{
    background: #fef3e2;
    color: var(--cite-med);
}}

.cite-low {{
    background: #f0f0f5;
    color: var(--cite-low);
}}

.footer {{
    text-align: center;
    padding: 1.5rem 0;
    margin-top: 1rem;
    border-top: 1px solid var(--border);
    font-size: 0.75rem;
    color: var(--text-muted);
}}

.footer a {{
    color: var(--accent);
    text-decoration: none;
}}

@media (max-width: 600px) {{
    .container {{
        padding: 1rem;
    }}
    .stat-number {{
        font-size: 1.4rem;
    }}
    .stat-label {{
        font-size: 0.65rem;
    }}
    .stat-card {{
        padding: 0.8rem 0.5rem;
    }}
}}
</style>
</head>
<body>
<div class="container">
    <div class="stats-banner">
        <div class="stat-card">
            <div class="stat-number">{total_pubs}</div>
            <div class="stat-label">Publications</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{stats.get('total_citations', 0)}</div>
            <div class="stat-label">Citations</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{stats.get('h_index', 0)}</div>
            <div class="stat-label">h-index</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{stats.get('i10_index', 0)}</div>
            <div class="stat-label">i10-index</div>
        </div>
    </div>

    {pub_sections}

    <div class="footer">
        Auto-updated from <a href="https://scholar.google.com/citations?user={SCHOLAR_ID}" target="_blank">Google Scholar</a> on {now}<br>
        Powered by GitHub Actions + SerpAPI
    </div>
</div>
</body>
</html>"""
    
    return html


def main():
    if not SERPAPI_KEY:
        print("ERROR: SERPAPI_KEY environment variable is not set!")
        print("Please add your SerpAPI key as a GitHub repository secret.")
        exit(1)
    
    print("=" * 50)
    print("NIE LAB Publication Updater")
    print("=" * 50)
    
    print("\n[1/3] Fetching citation statistics...")
    stats = get_author_info()
    print(f"  Citations: {stats['total_citations']}, h-index: {stats['h_index']}, i10-index: {stats['i10_index']}")
    
    print("\n[2/3] Fetching publications...")
    publications = get_publications(MAX_PAPERS)
    print(f"  Found {len(publications)} publications")
    
    print("\n[3/3] Generating HTML...")
    
    os.makedirs("docs", exist_ok=True)
    
    # Save JSON data
    data = {
        "updated": datetime.utcnow().isoformat(),
        "scholar_id": SCHOLAR_ID,
        "stats": stats,
        "publications": publications
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Saved JSON to {OUTPUT_JSON}")
    
    # Generate and save HTML
    html = generate_html(publications, stats)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Saved HTML to {OUTPUT_HTML}")
    
    print("\n✅ Done! Publication page updated successfully.")


if __name__ == "__main__":
    main()
