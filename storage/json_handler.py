
import json
from pathlib import Path
from datetime import datetime
from typing import Any

from models.lead import Lead


def _ensure_directory(filepath: str) -> None:
    """Create directory if it doesn't exist."""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)


def _lead_from_dict(data: dict[str, Any]) -> Lead:
    """Convert dictionary to Lead object with validation."""
    # Parse timestamp back to datetime
    data['timestamp'] = datetime.fromisoformat(data['timestamp'])
    # Lead.__init__ will call validate() via __post_init__
    return Lead(**data)


def save_leads(leads: list[Lead], filename: str) -> None:
    """Save leads to JSON file."""
    _ensure_directory(filename)
    
    leads_data = [lead.to_dict() for lead in leads]
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(leads_data, f, indent=2, ensure_ascii=False)
    
    print(f"Saved {len(leads)} leads to {filename}")


def load_leads(filename: str) -> list[Lead]:
    """Load leads from JSON file."""
    if not Path(filename).exists():
        print(f"File {filename} does not exist, returning empty list")
        return []
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            leads_data = json.load(f)
        
        leads = [_lead_from_dict(data) for data in leads_data]
        print(f"Loaded {len(leads)} leads from {filename}")
        return leads
    
    except Exception as e:
        print(f"Error loading leads from {filename}: {e}")
        return []


def append_leads(leads: list[Lead], filename: str) -> None:
    """Append new leads to existing file, removing duplicates based on URL."""
    existing_leads = load_leads(filename)

    # Create set of existing URLs for fast lookup
    existing_urls = {lead.url for lead in existing_leads}

    # Filter out duplicates
    new_leads = [lead for lead in leads if lead.url not in existing_urls]

    if not new_leads:
        print(f"No new leads to append (all {len(leads)} were duplicates)")
        return

    # IMPROVED (ISSUE #4): Calculate statistics by source and type
    reddit_leads = [l for l in new_leads if l.source == 'reddit']
    search_leads = [l for l in reddit_leads if l.metadata.get('targeted_search')]
    subreddit_leads = [l for l in reddit_leads if not l.metadata.get('targeted_search')]
    other_sources = [l for l in new_leads if l.source != 'reddit']

    # Combine and save
    all_leads = existing_leads + new_leads
    save_leads(all_leads, filename)

    # IMPROVED: Enhanced output with breakdown
    print(f"Appended {len(new_leads)} new leads ({len(leads) - len(new_leads)} duplicates removed)")

    # Show breakdown by source
    if reddit_leads:
        print(f"   • Reddit: {len(reddit_leads)} leads")
        if search_leads:
            print(f"     - Targeted search: {len(search_leads)} leads")
        if subreddit_leads:
            print(f"     - Subreddit scraping: {len(subreddit_leads)} leads")

    if other_sources:
        # Group other sources
        from collections import Counter
        source_counts = Counter(l.source for l in other_sources)
        for source, count in source_counts.items():
            print(f"   • {source.title()}: {count} leads")


def get_lead_count(filename: str) -> int:
    """Get count of leads in file without loading all data."""
    if not Path(filename).exists():
        return 0
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return len(data)
    except Exception:
        return 0
