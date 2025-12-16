

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

        IMPROVED: Source-aware validation with stricter Reddit rules.
        - Reddit: Min 12 words, subreddit-aware engagement (0-2+ based on subreddit type)
        - Other sources: Min 10 words, engagement score 1+
        - Spam filtering (enhanced checks for promotional content)
        """
        # IMPROVED: Stricter source-aware rules
        if self.source == 'reddit':
            min_words = 12          # More substantive content required

            # SUBREDDIT-AWARE: Different engagement thresholds by subreddit type
            subreddit = self.subreddit or ""
            HELP_SEEKING = ['forhire', 'slavelabour', 'Jobs4Bitcoins', 'hire']
            is_help_subreddit = any(sub in subreddit.lower() for sub in HELP_SEEKING)

            if is_help_subreddit:
                min_engagement = 0  # OK to have 0 upvotes in r/forhire (fast responses)
            else:
                min_engagement = 2  # General subreddits need validation (2+ upvotes)
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

        # Filter 3: Enhanced spam detection
        if self._is_likely_spam():
            return False

        return True
    
    def _is_likely_spam(self) -> bool:
        """
        Enhanced spam detection to filter obvious promotional content.
        Returns True if content is likely spam.
        """
        content_lower = self.content.lower()

        # IMPROVED: Expanded spam indicators
        spam_phrases = [
            # Existing
            'click here', 'buy now', 'limited time offer', 'act now',
            'sign up today', 'free trial', 'no credit card', 'risk free',
            'dm for details', 'check out my', 'follow me', 'subscribe',
            '🚀🚀🚀', '💰💰💰', 'crypto giveaway', 'airdrop', 'pump and dump',

            # NEW: Reddit-specific spam
            'upvote this', 'upvote if you', 'join our discord', 'dm me',
            'check my profile', 'check my page', 'visit my website',
            'link in bio', 'comment below', 'drop a comment',
            'follow for more', 'join our community', 'join us at',

            # NEW: Crypto scams
            'guaranteed profit', 'passive income', '100x', '1000x',
            'to the moon', 'wen moon', 'wen lambo', 'rugpull',

            # NEW: Self-promotion
            'i just launched', 'i built this', 'my new app', 'my startup',
            'our new platform', 'we just released', 'proud to share'
        ]

        # IMPROVED: Lower threshold from 3 to 2
        spam_count = sum(1 for phrase in spam_phrases if phrase in content_lower)
        if spam_count >= 2:
            return True

        # NEW: Check for excessive emoji (spam indicator)
        emoji_count = sum(1 for char in self.content if ord(char) > 127)
        if emoji_count > 10:  # More than 10 emojis = spam
            return True

        # NEW: Check for sketchy domains
        sketchy_domains = ['.tk', '.ml', '.ga', '.cf', 'bit.ly', 'tinyurl.com']
        if any(domain in content_lower for domain in sketchy_domains):
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
