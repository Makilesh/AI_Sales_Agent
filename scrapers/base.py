"""Base scraper class for all platform scrapers."""

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime

from models.lead import Lead


class BaseScraper(ABC):
    """Abstract base class for platform-specific scrapers."""
    
    def __init__(self, keywords: list[str], rate_limit: int, days_filter: int = 30) -> None:
        """
        Initialize the scraper.
        
        Args:
            keywords: List of keywords to filter leads
            rate_limit: Maximum requests per time period (implementation-specific)
            days_filter: Only include content from last N days (0 = no filter, default: 30)
        """
        self.keywords = keywords
        self.rate_limit = rate_limit
        self.days_filter = days_filter
        self.last_request_time: datetime | None = None
        self._request_count = 0
    
    @abstractmethod
    async def scrape(self) -> list[Lead]:
        """
        Scrape leads from the platform.
        
        Returns:
            List of Lead objects
        """
        pass
    
    def _should_scrape(self, text: str) -> bool:
        """Check if text contains any of the target keywords."""
        if not text:
            return False
        
        text_lower = text.lower()
        return any(keyword.lower() in text_lower for keyword in self.keywords)
    
    def _is_within_date_range(self, content_date: datetime) -> bool:
        """Check if content is within the date filter range."""
        if self.days_filter <= 0:
            return True  # No filter
        
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=self.days_filter)
        return content_date >= cutoff_date
    
    async def _apply_rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        if self.last_request_time is None:
            self.last_request_time = datetime.now()
            return
        
        # Calculate delay based on rate limit
        # NOTE: Subclasses should override if using different time units
        # Default: rate_limit is requests per minute
        delay_seconds = 60.0 / self.rate_limit if self.rate_limit > 0 else 1.0
        
        elapsed = (datetime.now() - self.last_request_time).total_seconds()
        
        if elapsed < delay_seconds:
            wait_time = delay_seconds - elapsed
            await asyncio.sleep(wait_time)
        
        self.last_request_time = datetime.now()
        self._request_count += 1
    
    def _filter_leads(self, leads: list[Lead]) -> list[Lead]:
        """Filter leads based on keywords and basic criteria."""
        return [
            lead for lead in leads
            if self._should_scrape(lead.content) or 
               (lead.title and self._should_scrape(lead.title))
        ]
    
    async def scrape_with_rate_limit(self) -> list[Lead]:
        """
        Scrape leads with automatic rate limiting.
        
        Returns:
            Filtered list of Lead objects
        """
        await self._apply_rate_limit()
        leads = await self.scrape()
        return self._filter_leads(leads)
    
    def get_stats(self) -> dict[str, int]:
        """Get scraper statistics."""
        return {
            'request_count': self._request_count,
            'keyword_count': len(self.keywords)
        }
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(keywords={len(self.keywords)}, rate_limit={self.rate_limit})"
