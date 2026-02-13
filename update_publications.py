"""
NIE LAB Publication Auto-Updater (v3)
- SerpAPI for Google Scholar data
- OpenAlex API for Journal Impact Factors (free, no key needed)
- Corresponding author marking from manual list

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
IF_CACHE_FILE = "docs/if_cache.json"
CORRESPONDING_FILE = "corresponding_author.txt"
MAX_PAPERS = 200

SERPAPI_KEY = os.environ.get("SERPAPI_KEY", "")


# ============================================
# SerpAPI functions
# ============================================
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
    params = {"author_id": SCHOLAR_ID, "hl": "en"}
    data = serpapi_request(params)
    cited_by = data.get("cited_by", {}).get("table", [])
    stats = {"total_citations": 0, "h_index": 0, "i10_index": 0}
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
            "author_id": SCHOLAR_ID, "hl": "en",
            "start": start, "num": 100, "sort": "pubdate"
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


# ============================================
# OpenAlex API for Impact Factor
# ============================================
def load_if_cache():
    """Load cached IF values."""
    if os.path.exists(IF_CACHE_FILE):
        with open(IF_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_if_cache(cache):
    """Save IF cache."""
    with open(IF_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def normalize_journal_name(name):
    """Normalize journal name for matching."""
    if not name:
        return ""
    # Remove volume, issue, page info
    # e.g., "Advanced Materials 35 (12), 2417539" -> "Advanced Materials"
    import re
    # Remove everything after first number sequence that looks like volume
    cleaned = re.split(r'\s+\d+\s*[\(,]', name)[0].strip()
    # Remove trailing commas, dots
    cleaned = cleaned.rstrip('.,; ')
    return cleaned.lower()


def get_journal_if(journal_name, cache):
    """Get Impact Factor for a journal using OpenAlex API."""
    normalized = normalize_journal_name(journal_name)
    if not normalized:
        return None
    
    # Check cache first
    if normalized in cache:
        return cache[normalized]
    
    try:
        query = urllib.parse.quote(normalized)
        url = f"https://api.openalex.org/sources?search={query}&per_page=1&mailto=nielab@pknu.ac.kr"
        req = urllib.request.Request(url, headers={
            "User-Agent": "NIELab-Publication-Updater/1.0"
        })
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        
        results = data.get("results", [])
        if results:
            source = results[0]
            # OpenAlex provides 2-year mean citedness (similar to IF)
            summary = source.get("summary_stats", {})
            impact = summary.get("2yr_mean_citedness")
            if impact is not None:
                impact = round(impact, 1)
            cache[normalized] = impact
            return impact
        
        cache[normalized] = None
        return None
        
    except Exception as e:
        print(f"    Warning: Could not fetch IF for '{normalized}': {e}")
        return None


def get_all_impact_factors(publications):
    """Get IF values for all unique journals."""
    cache = load_if_cache()
    
    # Collect unique journal names
    journals = set()
    for pub in publications:
        normalized = normalize_journal_name(pub.get("venue", ""))
        if normalized and normalized not in cache:
            journals.add(normalized)
    
    print(f"  Looking up IF for {len(journals)} new journals...")
    
    for i, journal in enumerate(journals):
        # Re-create the original-ish name for search
        get_journal_if(journal, cache)
        if (i + 1) % 10 == 0:
            print(f"    Processed {i + 1}/{len(journals)}...")
        time.sleep(0.2)  # Rate limiting for OpenAlex
    
    save_if_cache(cache)
    return cache


# ============================================
# Corresponding Author management
# ============================================
def load_corresponding_papers():
    """Load list of papers where the PI is corresponding author.
    
    File format (corresponding_author.txt):
    - One paper title per line (can be partial match)
    - Lines starting with # are comments
    - Empty lines are ignored
    """
    papers = []
    if os.path.exists(CORRESPONDING_FILE):
        with open(CORRESPONDING_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    papers.append(line.lower())
    return papers


def is_corresponding_author(pub_title, corresponding_list):
    """Check if the PI is corresponding author of this paper."""
    title_lower = pub_title.lower()
    for pattern in corresponding_list:
        if pattern in title_lower or title_lower in pattern:
            return True
    return False


# ============================================
# HTML Generation
# ============================================
def generate_html(publications, stats, if_cache, corresponding_list):
    """Generate HTML page with IF and corresponding author info."""
    
    pubs_by_year = {}
    for pub in publications:
        year = pub.get("year", 0)
        year_key = str(year) if year > 0 else "Other"
        if year_key not in pubs_by_year:
            pubs_by_year[year_key] = []
        pubs_by_year[year_key].append(pub)
    
    sorted_years = sorted(
        [y for y in pubs_by_year.keys() if y != "Other"],
        key=lambda x: int(x), reverse=True
    )
    if "Other" in pubs_by_year:
        sorted_years.append("Other")
    
    total_pubs = len(publications)
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    
    pub_sections = ""
    for year in sorted_years:
        pubs = pubs_by_year[year]
        pubs_sorted = sorted(pubs, key=lambda x: x.get("citations") or 0, reverse=True)
        
        items = ""
        for pub in pubs_sorted:
            title = pub.get("title", "Untitled")
            authors = pub.get("authors", "")
            venue = pub.get("venue", "")
            citations = pub.get("citations") or 0
            link = pub.get("link", "#")
            
            # Check corresponding author
            is_corresponding = is_corresponding_author(title, corresponding_list)
            
            # Highlight PI name with corresponding author mark
            if is_corresponding:
                authors_html = authors.replace("EK Lee", "<strong>EK Lee*</strong>")
                authors_html = authors_html.replace("E Lee", "<strong>E Lee*</strong>")
                authors_html = authors_html.replace("E.K. Lee", "<strong>E.K. Lee*</strong>")
            else:
                authors_html = authors.replace("EK Lee", "<strong>EK Lee</strong>")
                authors_html = authors_html.replace("E Lee", "<strong>E Lee</strong>")
                authors_html = authors_html.replace("E.K. Lee", "<strong>E.K. Lee</strong>")
            
            # Get Impact Factor
            normalized_venue = normalize_journal_name(venue)
            impact_factor = if_cache.get(normalized_venue)
            
            # Build venue display with IF
            venue_display = venue
            if impact_factor and impact_factor > 0:
                venue_display = f'{venue} <span class="if-badge">IF: {impact_factor}</span>'
            
            # Citation badge
            citation_badge = ""
            if citations and citations > 0:
                badge_class = "cite-high" if citations >= 50 else ("cite-med" if citations >= 10 else "cite-low")
                citation_badge = f'<span class="cite-badge {badge_class}">{citations} citations</span>'
            
            # Corresponding author indicator
            corr_mark = ""
            if is_corresponding:
                corr_mark = '<span class="corr-badge">✉ Corresponding</span>'
            
            items += f"""
            <div class="pub-item">
                <div class="pub-title"><a href="{link}" target="_blank" rel="noopener">{title}</a></div>
                <div class="pub-authors">{authors_html}</div>
                <div class="pub-venue">{venue_display}</div>
                <div class="pub-badges">
                    {citation_badge}
                    {corr_mark}
                </div>
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

.legend {{
    display: flex;
    gap: 1.2rem;
    margin-bottom: 1.2rem;
    font-size: 0.75rem;
    color: var(--text-muted);
    flex-wrap: wrap;
}}

.legend-item {{
    display: flex;
    align-items: center;
    gap: 0.3rem;
}}

.stats-banner {{
    display: flex;
    gap: 1px;
    background: var(--border);
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 1.5rem;
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

.pub-badges {{
    display: flex;
    gap: 0.5rem;
    flex-wrap: wrap;
    margin-top: 0.35rem;
}}

.cite-badge {{
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 0.15rem 0.5rem;
    border-radius: 10px;
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

.if-badge {{
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 600;
    font-style: normal;
    padding: 0.1rem 0.45rem;
    border-radius: 8px;
    background: #e8f5e9;
    color: #2e7d32;
    margin-left: 0.3rem;
    vertical-align: middle;
}}

.corr-badge {{
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 600;
    padding: 0.15rem 0.5rem;
    border-radius: 10px;
    background: var(--accent-light);
    color: var(--accent);
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

    <div class="legend">
        <div class="legend-item"><strong style="color:var(--accent)">EK Lee*</strong> = Corresponding author</div>
        <div class="legend-item"><span class="if-badge">IF: 0.0</span> = Impact Factor</div>
        <div class="legend-item"><span class="corr-badge">✉ Corresponding</span> = Corresponding author paper</div>
    </div>

    {pub_sections}

    <div class="footer">
        Auto-updated from <a href="https://scholar.google.com/citations?user={SCHOLAR_ID}" target="_blank">Google Scholar</a> on {now}<br>
        Impact Factors from <a href="https://openalex.org" target="_blank">OpenAlex</a> | Powered by GitHub Actions
    </div>
</div>
</body>
</html>"""
    
    return html


# ============================================
# Main
# ============================================
def main():
    if not SERPAPI_KEY:
        print("ERROR: SERPAPI_KEY environment variable is not set!")
        exit(1)
    
    print("=" * 50)
    print("NIE LAB Publication Updater v3")
    print("=" * 50)
    
    print("\n[1/5] Fetching citation statistics...")
    stats = get_author_info()
    print(f"  Citations: {stats['total_citations']}, h-index: {stats['h_index']}, i10-index: {stats['i10_index']}")
    
    print("\n[2/5] Fetching publications...")
    publications = get_publications(MAX_PAPERS)
    print(f"  Found {len(publications)} publications")
    
    print("\n[3/5] Fetching Impact Factors from OpenAlex...")
    if_cache = get_all_impact_factors(publications)
    matched = sum(1 for v in if_cache.values() if v and v > 0)
    print(f"  IF data available for {matched} journals")
    
    print("\n[4/5] Loading corresponding author list...")
    corresponding_list = load_corresponding_papers()
    print(f"  {len(corresponding_list)} papers marked as corresponding author")
    
    print("\n[5/5] Generating HTML...")
    os.makedirs("docs", exist_ok=True)
    
    data = {
        "updated": datetime.utcnow().isoformat(),
        "scholar_id": SCHOLAR_ID,
        "stats": stats,
        "publications": publications
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Saved JSON to {OUTPUT_JSON}")
    
    html = generate_html(publications, stats, if_cache, corresponding_list)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Saved HTML to {OUTPUT_HTML}")
    
    print("\n✅ Done! Publication page updated successfully.")


if __name__ == "__main__":
    main()
