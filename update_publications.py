"""
NIE LAB Publication Auto-Updater
Scrapes Google Scholar profile and generates a styled HTML page
for embedding in Google Sites.

Usage: python update_publications.py
"""

import json
import re
import time
import urllib.request
import urllib.parse
from html.parser import HTMLParser
from datetime import datetime

# ============================================
# 설정 (Configuration)
# ============================================
SCHOLAR_ID = "_ME8VaYAAAAJ"  # 교수님의 Google Scholar Profile ID
OUTPUT_HTML = "docs/index.html"
OUTPUT_JSON = "docs/publications.json"
MAX_PAPERS = 200  # 최대 가져올 논문 수


class ScholarParser(HTMLParser):
    """Simple HTML parser to extract publication data from Google Scholar."""
    
    def __init__(self):
        super().__init__()
        self.publications = []
        self.current_pub = {}
        self.capture = None
        self.in_pub_row = False
        self.tag_stack = []
        self.current_data = ""
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        
        if tag == "tr" and "gsc_a_tr" in cls:
            self.in_pub_row = True
            self.current_pub = {}
            
        if self.in_pub_row:
            if tag == "a" and "gsc_a_at" in cls:
                self.capture = "title"
                self.current_data = ""
                self.current_pub["link"] = "https://scholar.google.com" + attrs_dict.get("href", "")
            elif "gsc_a_at" in cls and tag == "td":
                self.capture = "title_cell"
            elif tag == "span" and "gs_gray" in cls:
                self.capture = "gray"
                self.current_data = ""
            elif tag == "a" and "gsc_a_ac" in cls:
                self.capture = "citations"
                self.current_data = ""
            elif tag == "span" and "gsc_a_h" in cls:
                self.capture = "year"
                self.current_data = ""
                
    def handle_endtag(self, tag):
        if self.capture == "title" and tag == "a":
            self.current_pub["title"] = self.current_data.strip()
            self.capture = None
        elif self.capture == "gray" and tag == "span":
            if "authors" not in self.current_pub:
                self.current_pub["authors"] = self.current_data.strip()
            else:
                self.current_pub["venue"] = self.current_data.strip()
            self.capture = None
        elif self.capture == "citations" and tag == "a":
            cite_text = self.current_data.strip()
            self.current_pub["citations"] = int(cite_text) if cite_text.isdigit() else 0
            self.capture = None
        elif self.capture == "year" and tag == "span":
            year_text = self.current_data.strip()
            self.current_pub["year"] = int(year_text) if year_text.isdigit() else 0
            self.capture = None
            
        if tag == "tr" and self.in_pub_row:
            self.in_pub_row = False
            if self.current_pub.get("title"):
                self.publications.append(self.current_pub)
                
    def handle_data(self, data):
        if self.capture:
            self.current_data += data


class ScholarStatsParser(HTMLParser):
    """Parse citation stats from the profile page."""
    
    def __init__(self):
        super().__init__()
        self.stats = {}
        self.in_stats_table = False
        self.capture = None
        self.current_data = ""
        self.stat_values = []
        
    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        cls = attrs_dict.get("class", "")
        
        if tag == "td" and "gsc_rsb_std" in cls:
            self.capture = "stat_value"
            self.current_data = ""
            
    def handle_endtag(self, tag):
        if self.capture == "stat_value" and tag == "td":
            self.stat_values.append(self.current_data.strip())
            self.capture = None
            
    def handle_data(self, data):
        if self.capture:
            self.current_data += data


def fetch_scholar_page(scholar_id, start=0):
    """Fetch a page from Google Scholar profile."""
    base_url = "https://scholar.google.com/citations"
    params = {
        "user": scholar_id,
        "hl": "en",
        "cstart": start,
        "pagesize": 100,
        "sortby": "pubdate"
    }
    url = f"{base_url}?{urllib.parse.urlencode(params)}"
    
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    })
    
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def get_publications(scholar_id, max_papers=200):
    """Get all publications from Google Scholar profile."""
    all_pubs = []
    start = 0
    
    while len(all_pubs) < max_papers:
        print(f"  Fetching publications starting from {start}...")
        html = fetch_scholar_page(scholar_id, start)
        
        parser = ScholarParser()
        parser.feed(html)
        
        if not parser.publications:
            break
            
        all_pubs.extend(parser.publications)
        
        if len(parser.publications) < 100:
            break
            
        start += 100
        time.sleep(2)  # Rate limiting
    
    return all_pubs[:max_papers]


def get_stats(scholar_id):
    """Get citation statistics from profile."""
    html = fetch_scholar_page(scholar_id)
    parser = ScholarStatsParser()
    parser.feed(html)
    
    stats = {
        "total_citations": 0,
        "h_index": 0,
        "i10_index": 0
    }
    
    # Google Scholar stats table: [All citations, Recent citations, All h-index, Recent h-index, All i10, Recent i10]
    values = parser.stat_values
    if len(values) >= 6:
        try:
            stats["total_citations"] = int(values[0]) if values[0] else 0
            stats["h_index"] = int(values[2]) if values[2] else 0
            stats["i10_index"] = int(values[4]) if values[4] else 0
        except (ValueError, IndexError):
            pass
    
    return stats


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
        pubs_sorted = sorted(pubs, key=lambda x: x.get("citations", 0), reverse=True)
        
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
            if citations > 0:
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

/* Stats Banner */
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

/* Year Sections */
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

/* Publication Items */
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

/* Footer */
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

/* Responsive */
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
    .stats-banner {{
        flex-direction: row;
    }}
    .stat-card {{
        padding: 0.8rem 0.5rem;
    }}
}}
</style>
</head>
<body>
<div class="container">
    <!-- Citation Stats -->
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

    <!-- Publications List -->
    {pub_sections}

    <div class="footer">
        Auto-updated from <a href="https://scholar.google.com/citations?user={SCHOLAR_ID}" target="_blank">Google Scholar</a> on {now}<br>
        Powered by GitHub Actions
    </div>
</div>
</body>
</html>"""
    
    return html


def main():
    print("=" * 50)
    print("NIE LAB Publication Updater")
    print("=" * 50)
    
    print("\n[1/3] Fetching citation statistics...")
    stats = get_stats(SCHOLAR_ID)
    print(f"  Citations: {stats['total_citations']}, h-index: {stats['h_index']}, i10-index: {stats['i10_index']}")
    
    print("\n[2/3] Fetching publications...")
    publications = get_publications(SCHOLAR_ID, MAX_PAPERS)
    print(f"  Found {len(publications)} publications")
    
    print("\n[3/3] Generating HTML...")
    
    # Ensure output directory exists
    import os
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
