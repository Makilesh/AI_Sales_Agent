

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


@dataclass
class Lead:
    """Represents a scraped lead from any platform."""
    
    source: str  # 'reddit', 'discord', 'slack'
    author: str
    content: str
    timestamp: datetime
    url: str
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # Optional fields
    title: str | None = None
    engagement_score: int = 0  # upvotes, reactions, etc.
    channel_name: str | None = None
    subreddit: str | None = None
    linkedin_post_type: str | None = None  # 'post', 'article', 'video', 'comment'
    
    # LLM qualification result (populated after qualification)
    qualification_result: dict[str, Any] | None = None
    
    def __post_init__(self) -> None:
        """Validate lead data after initialization."""
        self.validate()
    
    def validate(self) -> None:
        """Validate required fields and data types."""
        if not self.source:
            raise ValueError("Source cannot be empty")
        
        if self.source not in {'reddit', 'discord', 'slack', 'linkedin', 'linkedin_public'}:
            raise ValueError(f"Invalid source: {self.source}")
        
        if not self.author or not self.author.strip():
            raise ValueError("Author cannot be empty")
        
        if not self.content or not self.content.strip():
            raise ValueError("Content cannot be empty")

        # IMPROVED: Truncate long content instead of rejecting (Reddit posts can be very long)
        if len(self.content) > 10000:
            self.content = self.content[:10000] + "... [content truncated]"
        
        if not self.url or not self.url.startswith(('http://', 'https://')):
            raise ValueError("Invalid URL format")
        
        if not isinstance(self.timestamp, datetime):
            raise ValueError("Timestamp must be a datetime object")
    
    def to_dict(self) -> dict[str, Any]:
        """Convert lead to dictionary for JSON serialization."""
        data = asdict(self)
        # Convert datetime to ISO format string
        data['timestamp'] = self.timestamp.isoformat()
        return data
    
    def matches_keywords(self, keywords: list[str]) -> bool:
        """Check if lead content matches any of the provided keywords."""
        content_lower = self.content.lower()
        title_lower = self.title.lower() if self.title else ""
        
        return any(
            keyword.lower() in content_lower or keyword.lower() in title_lower
            for keyword in keywords
        )
    
    def is_qualified(self, min_engagement: int = 1) -> bool:
        """
        Check if lead meets basic qualification criteria.

        IMPROVED (ISSUE #5): Source-aware validation with relaxed rules for Reddit.
        - Reddit: Min 8 words, engagement score 0+ (brand new posts)
        - Other sources: Min 10 words, engagement score 1+
        - Spam filtering (basic checks for promotional content)
        """
        # IMPROVED: Source-aware rules (Reddit is more relaxed)
        if self.source == 'reddit':
            min_words = 8           # Very brief service requests like "[Hiring] RWA dev"
            min_engagement = 0      # Accept brand new posts (score=0)
        else:
            min_words = 10
            # Use the provided min_engagement parameter for other sources

        # Filter 1: Minimum word count (source-aware)
        word_count = len(self.content.split())
        if word_count < min_words:
            return False

        # Filter 2: Minimum engagement score (source-aware)
        if self.engagement_score < min_engagement:
            return False
        
        # Filter 3: Basic spam detection
        if self._is_likely_spam():
            return False
        
        return True
    
    def _is_likely_spam(self) -> bool:
        """
        Basic spam detection to filter obvious promotional content.
        Returns True if content is likely spam.
        """
        content_lower = self.content.lower()
        
        # Spam indicators
        spam_phrases = [
            'click here', 'buy now', 'limited time offer', 'act now',
            'sign up today', 'free trial', 'no credit card', 'risk free',
            'dm for details', 'check out my', 'follow me', 'subscribe',
            '🚀🚀🚀', '💰💰💰', 'crypto giveaway', 'airdrop', 'pump and dump'
        ]
        
        # Check for multiple spam phrases
        spam_count = sum(1 for phrase in spam_phrases if phrase in content_lower)
        
        # If multiple spam indicators, likely spam
        if spam_count >= 3:
            return True
        
        # Check for excessive promotional language
        promo_words = ['buy', 'sale', 'discount', 'offer', 'deal', 'free']
        promo_count = sum(1 for word in promo_words if word in content_lower)
        
        # If content is short and heavily promotional, likely spam
        if word_count := len(self.content.split()) < 30 and promo_count >= 4:
            return True
        
        return False
    
    def __repr__(self) -> str:
        """String representation of the lead."""
        content_preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"Lead(source={self.source}, author={self.author}, content='{content_preview}')"
