"""
NIE LAB Publication Auto-Updater (v5 - OpenAlex)
- 100% OpenAlex API (free, no paid API needed)
- Full author names (no truncation)
- Journal Impact Factor included
- Citation counts included

Usage: python update_publications.py
Optional: OPENALEX_API_KEY environment variable (free, get from https://openalex.org/login)
"""

import json
import os
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime

# ============================================
# 설정 (Configuration)
# ============================================
ORCID = "0000-0001-5727-5716"  # 교수님 ORCID
PI_NAME = "Eun Kwang Lee"  # Display name for highlighting
OUTPUT_HTML = "docs/index.html"
OUTPUT_JSON = "docs/publications.json"
MAILTO = "nielab@pknu.ac.kr"  # OpenAlex polite pool (faster responses)

# Optional: OpenAlex API key for higher rate limits
OPENALEX_API_KEY = os.environ.get("OPENALEX_API_KEY", "")


# ============================================
# OpenAlex API
# ============================================
def openalex_request(endpoint, params=None):
    """Make a request to OpenAlex API."""
    if params is None:
        params = {}
    params["mailto"] = MAILTO
    if OPENALEX_API_KEY:
        params["api_key"] = OPENALEX_API_KEY
    
    url = f"https://api.openalex.org/{endpoint}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": f"NIELab/1.0 (mailto:{MAILTO})"})
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"    Retry {attempt + 1}: {e}")
                time.sleep(2)
            else:
                raise


def get_author_info():
    """Get author profile and stats from OpenAlex."""
    data = openalex_request(f"authors/orcid:{ORCID}")
    
    stats = {
        "total_citations": data.get("cited_by_count", 0),
        "works_count": data.get("works_count", 0),
        "h_index": data.get("summary_stats", {}).get("h_index", 0),
        "i10_index": data.get("summary_stats", {}).get("i10_index", 0),
        "author_id": data.get("id", ""),
        "display_name": data.get("display_name", PI_NAME),
    }
    return stats


def get_publications():
    """Get all publications by the author from OpenAlex."""
    all_pubs = []
    cursor = "*"
    page = 1
    
    while True:
        print(f"  Fetching page {page}...")
        params = {
            "filter": f"author.orcid:{ORCID}",
            "sort": "publication_date:desc",
            "per_page": 100,
            "cursor": cursor,
            "select": "id,title,authorships,primary_location,publication_date,publication_year,cited_by_count,doi,type"
        }
        data = openalex_request("works", params)
        results = data.get("results", [])
        
        if not results:
            break
        
        for work in results:
            # Get full author list
            authors = []
            pi_position = None
            for i, authorship in enumerate(work.get("authorships", [])):
                author_name = authorship.get("author", {}).get("display_name", "")
                if author_name:
                    authors.append(author_name)
                # Check if this is the PI
                author_orcid = authorship.get("author", {}).get("orcid", "")
                if author_orcid and ORCID in author_orcid:
                    pi_position = i
            
            # Get journal/source info
            location = work.get("primary_location", {}) or {}
            source = location.get("source", {}) or {}
            journal_name = source.get("display_name", "")
            source_id = source.get("id", "")
            
            # Get DOI link
            doi = work.get("doi", "")
            link = doi if doi else ""
            
            pub = {
                "title": work.get("title", "Untitled"),
                "authors": ", ".join(authors),
                "authors_list": authors,
                "venue": journal_name,
                "source_id": source_id,
                "year": work.get("publication_year", 0) or 0,
                "date": work.get("publication_date", ""),
                "citations": work.get("cited_by_count", 0) or 0,
                "doi": doi,
                "link": link,
                "type": work.get("type", ""),
                "pi_position": pi_position,
                "openalex_id": work.get("id", ""),
            }
            all_pubs.append(pub)
        
        # Pagination
        meta = data.get("meta", {})
        cursor = meta.get("next_cursor")
        if not cursor:
            break
        page += 1
        time.sleep(0.2)
    
    return all_pubs


def get_impact_factors(publications):
    """Get Impact Factors for all unique journals."""
    # Collect unique source IDs
    source_ids = set()
    for pub in publications:
        sid = pub.get("source_id", "")
        if sid:
            source_ids.add(sid)
    
    print(f"  Looking up IF for {len(source_ids)} journals...")
    if_map = {}
    
    for i, source_id in enumerate(source_ids):
        try:
            # Extract the short ID
            short_id = source_id.split("/")[-1] if "/" in source_id else source_id
            data = openalex_request(f"sources/{short_id}", {"select": "id,display_name,summary_stats"})
            
            summary = data.get("summary_stats", {})
            impact = summary.get("2yr_mean_citedness")
            if impact is not None:
                impact = round(impact, 1)
            
            if_map[source_id] = {
                "name": data.get("display_name", ""),
                "if": impact
            }
        except Exception as e:
            print(f"    Warning: Could not fetch IF for {source_id}: {e}")
        
        if (i + 1) % 20 == 0:
            print(f"    Processed {i + 1}/{len(source_ids)}...")
        time.sleep(0.1)
    
    return if_map


# ============================================
# HTML Generation
# ============================================
def generate_html(publications, stats, if_map):
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
            title = pub.get("title", "Untitled") or "Untitled"
            authors = pub.get("authors", "")
            venue = pub.get("venue", "")
            citations = pub.get("citations") or 0
            link = pub.get("link", "")
            source_id = pub.get("source_id", "")
            
            # Highlight PI name
            authors_html = authors
            for name_variant in [PI_NAME, "Eun Kwang Lee", "E. Lee", "E.K. Lee", "EK Lee"]:
                if name_variant in authors_html:
                    authors_html = authors_html.replace(name_variant, f"<strong>{name_variant}</strong>")
                    break
            
            # Impact Factor
            if_info = if_map.get(source_id, {})
            impact_factor = if_info.get("if")
            venue_display = venue
            if impact_factor and impact_factor > 0:
                venue_display = f'{venue} <span class="if-badge">IF: {impact_factor}</span>'
            
            # Citation badge
            citation_badge = ""
            if citations and citations > 0:
                badge_class = "cite-high" if citations >= 50 else ("cite-med" if citations >= 10 else "cite-low")
                citation_badge = f'<span class="cite-badge {badge_class}">{citations} citations</span>'
            
            # Link
            title_html = f'<a href="{link}" target="_blank" rel="noopener">{title}</a>' if link else title
            
            items += f"""
            <div class="pub-item">
                <div class="pub-title">{title_html}</div>
                <div class="pub-authors">{authors_html}</div>
                <div class="pub-venue">{venue_display}</div>
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

.pub-title {{
    font-weight: 600;
    font-size: 0.95rem;
    line-height: 1.4;
}}

.pub-title a {{
    color: var(--text-primary);
    text-decoration: none;
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
        Auto-updated from <a href="https://openalex.org" target="_blank">OpenAlex</a> on {now}<br>
        <a href="https://scholar.google.com/citations?user=_ME8VaYAAAAJ" target="_blank">Google Scholar Profile</a> |
        <a href="https://orcid.org/{ORCID}" target="_blank">ORCID</a> |
        Powered by GitHub Actions
    </div>
</div>
</body>
</html>"""
    
    return html


def main():
    print("=" * 50)
    print("NIE LAB Publication Updater v5 (OpenAlex)")
    print("=" * 50)
    
    print("\n[1/4] Fetching author profile...")
    stats = get_author_info()
    print(f"  {stats['display_name']}: {stats['total_citations']} citations, h-index: {stats['h_index']}, i10-index: {stats['i10_index']}")
    
    print("\n[2/4] Fetching publications...")
    publications = get_publications()
    print(f"  Found {len(publications)} publications")
    
    print("\n[3/4] Fetching Impact Factors...")
    if_map = get_impact_factors(publications)
    matched = sum(1 for v in if_map.values() if v.get("if") and v["if"] > 0)
    print(f"  IF data available for {matched} journals")
    
    print("\n[4/4] Generating HTML...")
    os.makedirs("docs", exist_ok=True)
    
    # Save JSON
    data = {
        "updated": datetime.utcnow().isoformat(),
        "orcid": ORCID,
        "stats": stats,
        "publications": publications
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  Saved JSON to {OUTPUT_JSON}")
    
    # Generate HTML
    html = generate_html(publications, stats, if_map)
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Saved HTML to {OUTPUT_HTML}")
    
    print(f"\n✅ Done! {len(publications)} publications updated successfully.")


if __name__ == "__main__":
    main()
