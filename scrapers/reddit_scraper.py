
import asyncio
import traceback  # FIX: Added for debug mode stack traces
import warnings  # FIX: Suppress PRAW async warnings
from datetime import datetime, timedelta

import praw
from praw.models import Submission

from config.settings import settings  # FIX: Added for debug_mode access
from models.lead import Lead
from scrapers.base import BaseScraper

# FIX: Suppress PRAW async environment warnings (non-breaking, code works correctly)
warnings.filterwarnings('ignore', message='.*PRAW.*asynchronous.*')
warnings.filterwarnings('ignore', message='.*It is strongly recommended to use Async PRAW.*')


class RedditScraper(BaseScraper):
    """
    OPTIMIZED: Scraper for Reddit posts from targeted subreddits.

    Features:
    - Soft filtering with explicit inquiry signals
    - Posts only (comments removed)
    - Single-feed strategy (no hot/new overlap)
    - Time-based filtering with smart PRAW limits
    - Efficient rate limiting
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        keywords: list[str],
        subreddits: list[str],
        rate_limit: int = 100,
        days_filter: int = 30,
        skip_keyword_filter: bool = True
    ) -> None:
        """
        Initialize Reddit scraper.

        Args:
            client_id: Reddit API client ID
            client_secret: Reddit API client secret
            user_agent: Reddit API user agent
            keywords: Keywords to filter leads (if skip_keyword_filter=False)
            subreddits: List of subreddit names to scrape
            rate_limit: Requests per minute (default: 100)
            days_filter: Only include content from last N days (0 = no filter)
            skip_keyword_filter: If True, apply soft filter instead of keyword matching
        """
        super().__init__(keywords, rate_limit, days_filter)
        self.subreddits = subreddits
        self.skip_keyword_filter = skip_keyword_filter

        try:
            self.reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent
            )
            self.reddit.read_only = True
        except Exception as e:
            raise ValueError(f"Failed to initialize Reddit client: {e}")

    def _filter_leads(self, leads: list[Lead]) -> list[Lead]:
        """
        Smart keyword filtering for Reddit.

        Strategy:
        - When skip_keyword_filter=True: Apply soft filter (removes obvious non-inquiries)
        - When skip_keyword_filter=False: Apply strict keyword matching
        - Keeps all potential service requests while filtering spam/news/self-promotion

        Returns:
            Filtered list of leads
        """
        if self.skip_keyword_filter:
            # Apply soft filtering even when "disabled"
            # Removes obvious non-inquiries without requiring keyword match
            filtered = [lead for lead in leads if self._is_potential_inquiry(lead)]
            removed = len(leads) - len(filtered)
            if removed > 0:
                print(f"   🔍 Reddit: Soft filter removed {removed} obvious non-inquiries ({len(filtered)} passed)")
            else:
                print(f"   🔍 Reddit: Soft filter - {len(leads)} potential inquiries passed")
            return filtered
        else:
            # Strict keyword matching
            filtered = super()._filter_leads(leads)
            print(f"   🔍 Reddit: Keyword filter enabled - {len(filtered)}/{len(leads)} leads matched keywords")
            return filtered

    def _is_potential_inquiry(self, lead: Lead) -> bool:
        """
        OPTIMIZED: Soft filter with RWA-specific bypass logic.
        Removes spam/promotion while catching RWA exploratory language.

        Returns:
            True if lead has inquiry signals OR strong RWA intent, False otherwise
        """
        content_lower = lead.content.lower()
        title_lower = (lead.title or "").lower()
        full_text = f"{title_lower} {content_lower}"

        # BLOCK 1: Hard exclude patterns (spam/promotion/discussion)
        exclude_patterns = [
            "just launched", "proud to announce", "we released",
            "check out our", "i built", "i made", "my startup",
            "our product", "eli5", "explain like", "what do you think",
            "thoughts on", "is it just me", "does anyone else"
        ]
        if any(pattern in full_text for pattern in exclude_patterns):
            return False  # No exceptions - hard block
        
        # BLOCK 2: Service providers (offering services, not seeking)
        # Block BEFORE inquiry check to prevent false positives
        offering_patterns = [
            "[for hire]", "i offer", "my services include",
            "i can help with", "i specialize in", "my expertise",
            "portfolio:", "available for hire", "freelancer available"
        ]
        if any(pattern in full_text for pattern in offering_patterns):
            return False  # Service provider - hard block

        # PRIORITY 1: RWA-specific bypass (catches exploratory language)
        # These indicate RWA intent even without explicit inquiry signals
        rwa_intent_patterns = [
            # Explicit RWA actions with possessive (strong intent)
            "tokenize my", "tokenize our", "fractionalize my", "fractionalize our",
            # Exploratory RWA language (researching solutions)
            "exploring tokenization", "considering tokenization", "researching tokenization",
            "exploring fractional", "considering fractional", "researching fractional",
            # Need-based RWA (implicit inquiry)
            "need tokenization", "need to tokenize", "want to tokenize",
            "need fractional", "need asset tokenization",
            # Platform/service seeking (RWA-specific)
            "tokenization platform", "tokenization service", "tokenization consultant",
            "sto platform", "sto service", "security token offering",
            # Real estate + tokenization combo
            "real estate token", "property token", "tokenized real estate",
            "tokenize property", "tokenize real estate"
        ]
        
        if any(pattern in full_text for pattern in rwa_intent_patterns):
            return True  # RWA intent detected - bypass general inquiry check

        # PRIORITY 2: General inquiry signals (existing logic)
        inquiry_signals = [
            "looking for", "need help", "need someone", "need a",
            "anyone recommend", "recommendations for",
            "[hiring]", "[for hire]", "[task]", "hiring",
            "budget", "willing to pay", "can pay",
            "struggling with", "help with", "stuck on",
            "seeking", "best tool", "best platform", "best service",
            # Added exploratory signals for all services
            "exploring options", "considering options", "researching solutions",
            "evaluating platforms", "comparing services"
        ]

        return any(signal in full_text for signal in inquiry_signals)

    def _get_time_filter_for_praw(self) -> str:
        """
        Convert days_filter to PRAW time_filter parameter.

        Returns:
            'day', 'week', 'month', 'year', or 'all'
        """
        if self.days_filter == 0:
            return 'all'
        elif self.days_filter <= 1:
            return 'day'
        elif self.days_filter <= 7:
            return 'week'
        elif self.days_filter <= 30:
            return 'month'
        elif self.days_filter <= 365:
            return 'year'
        else:
            return 'all'

    async def scrape(self) -> list[Lead]:
        """
        OPTIMIZED: Scrape posts from specified subreddits (subreddit-only strategy).

        Returns:
            List of leads from subreddit posts
        """
        all_leads: list[Lead] = []

        # Print time filter info
        if self.days_filter > 0:
            cutoff_date = datetime.now() - timedelta(days=self.days_filter)
            time_filter = self._get_time_filter_for_praw()
            print(f"   🕒 Reddit: Filtering posts from last {self.days_filter} days (PRAW filter: '{time_filter}')")
            print(f"   📅 Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M')}")
        else:
            print(f"   ℹ️ Reddit: No time filter (fetching all posts)")

        # Scrape all subreddits (OPTIMIZED: removed targeted search)
        for subreddit_name in self.subreddits:
            try:
                leads = await self._scrape_subreddit(subreddit_name)
                all_leads.extend(leads)
            except Exception as e:
                print(f"❌ Reddit: Error scraping r/{subreddit_name}: {e}")
                if settings.debug_mode:
                    traceback.print_exc()
                continue

        return all_leads

    async def _scrape_subreddit(self, subreddit_name: str) -> list[Lead]:
        """
        OPTIMIZED: Scrape a single subreddit for posts only (comments removed).

        Args:
            subreddit_name: Name of subreddit (without r/ prefix)

        Returns:
            List of leads from subreddit posts
        """
        leads: list[Lead] = []

        try:
            # Wrap PRAW call in thread executor for true async
            subreddit = await asyncio.to_thread(self.reddit.subreddit, subreddit_name)

            # Calculate cutoff time for early stopping
            cutoff_time = datetime.now() - timedelta(days=self.days_filter) if self.days_filter > 0 else None

            # Helper to fetch posts with early date-based stopping
            def fetch_with_cutoff(generator, max_fetch=100):
                """Fetch posts but stop early if we hit old content."""
                posts = []
                old_post_count = 0

                for post in generator:
                    if cutoff_time:
                        post_date = datetime.fromtimestamp(post.created_utc)
                        if post_date < cutoff_time:
                            old_post_count += 1
                            # Stop if we've seen 5 old posts in a row (new/hot are chronological)
                            if old_post_count >= 5:
                                break
                            continue
                        else:
                            old_post_count = 0  # Reset counter on fresh post

                    posts.append(post)
                    if len(posts) >= max_fetch:
                        break

                return posts

            # OPTIMIZED: Single-feed strategy with smart limits (eliminates hot feed overlap)
            if self.days_filter <= 1:
                # Last 24 hours: Focus on NEW posts only
                new_posts = await asyncio.to_thread(lambda: fetch_with_cutoff(subreddit.new(limit=100), 50))
                hot_posts = []
                top_posts = []
            elif self.days_filter <= 7:
                # Last week: NEW + TOP (skip hot, it overlaps heavily)
                new_posts = await asyncio.to_thread(lambda: fetch_with_cutoff(subreddit.new(limit=80), 40))
                hot_posts = []
                top_posts = await asyncio.to_thread(lambda: list(subreddit.top(time_filter='week', limit=20)))
            elif self.days_filter <= 30:
                # Last month: TOP posts only (most engagement)
                new_posts = []
                hot_posts = []
                top_posts = await asyncio.to_thread(lambda: list(subreddit.top(time_filter='month', limit=50)))
            else:
                # Longer periods: Balanced approach
                new_posts = await asyncio.to_thread(lambda: fetch_with_cutoff(subreddit.new(limit=30), 20))
                hot_posts = []
                top_posts = await asyncio.to_thread(lambda: list(subreddit.top(time_filter='month', limit=30)))

            # Combine and deduplicate (all posts already filtered by date)
            all_posts = {post.id: post for post in hot_posts + new_posts + top_posts}.values()
            posts_to_process = list(all_posts)

            print(f"   📊 r/{subreddit_name}: Processing {len(posts_to_process)} posts within time range")

            # DEBUG: Uncomment for detailed post processing info
            # print(f"   DEBUG: Fetched {len(new_posts)} new, {len(hot_posts)} hot, {len(top_posts)} top posts")

            for submission in posts_to_process:
                # FIX (ISSUE #3): Rate limit once per post iteration
                # PRAW has built-in rate limiting, so we only control post processing speed
                await self._apply_rate_limit()

                # Check post only (OPTIMIZED: comments removed entirely)
                try:
                    post_lead = self._create_lead_from_post(submission, subreddit_name)
                    if post_lead:
                        leads.append(post_lead)
                except Exception as e:
                    print(f"⚠️ Reddit: Error processing post {submission.id} in r/{subreddit_name}: {e}")
                    if settings.debug_mode:
                        traceback.print_exc()
                    continue

        except Exception as e:
            # IMPROVED (ISSUE #4): Distinguish subreddit access errors
            print(f"❌ Reddit: Failed to access r/{subreddit_name}: {e}")
            if settings.debug_mode:
                traceback.print_exc()
            return []  # Return empty list instead of crashing

        return leads

    def _create_lead_from_post(self, submission: Submission, subreddit_name: str) -> Lead | None:
        """
        Create a Lead object from a Reddit post.

        Args:
            submission: PRAW Submission object
            subreddit_name: Name of subreddit

        Returns:
            Lead object or None if creation fails
        """
        try:
            # Check date filter
            post_date = datetime.fromtimestamp(submission.created_utc)
            if not self._is_within_date_range(post_date):
                return None

            content = f"{submission.title}\n\n{submission.selftext}" if submission.selftext else submission.title

            return Lead(
                source='reddit',
                author=str(submission.author) if submission.author else '[deleted]',
                content=content,
                timestamp=post_date,
                url=f"https://reddit.com{submission.permalink}",
                title=submission.title,
                engagement_score=submission.score,
                subreddit=subreddit_name,
                metadata={
                    'post_id': submission.id,
                    'num_comments': submission.num_comments,
                    'post_type': 'submission',
                    'is_self': submission.is_self
                }
            )
        except Exception as e:
            # IMPROVED (ISSUE #4): Include post ID if available
            post_id = getattr(submission, 'id', 'unknown')
            print(f"⚠️ Reddit: Error creating lead from post {post_id}: {e}")
            if settings.debug_mode:
                traceback.print_exc()
            return None

    def __repr__(self) -> str:
        """String representation showing configuration."""
        return (
            f"RedditScraper("
            f"subreddits={len(self.subreddits)}, "
            f"keywords={len(self.keywords)}, "
            f"skip_keyword_filter={self.skip_keyword_filter}"
            f")"
        )
