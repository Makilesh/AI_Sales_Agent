
import asyncio
import traceback  # FIX: Added for debug mode stack traces
import warnings  # FIX: Suppress PRAW async warnings
from datetime import datetime, timedelta

import praw
from praw.models import Submission, Comment

from config.settings import settings  # FIX: Added for debug_mode access
from models.lead import Lead
from scrapers.base import BaseScraper

# FIX: Suppress PRAW async environment warnings (non-breaking, code works correctly)
warnings.filterwarnings('ignore', message='.*PRAW.*asynchronous.*')
warnings.filterwarnings('ignore', message='.*It is strongly recommended to use Async PRAW.*')


class RedditScraper(BaseScraper):
    """
    Scraper for Reddit posts and comments.

    Features:
    - Optional keyword filtering (trust subreddit selection or enforce keywords)
    - Targeted search for high-intent service requests
    - Time-based filtering with dynamic PRAW limits
    - Efficient rate limiting (once per post)
    - Enhanced error logging with debug mode support
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
        skip_keyword_filter: bool = True,  # FIX: New parameter for Issue #1
        enable_search: bool = True  # FIX: New parameter for Issue #2
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
            skip_keyword_filter: If True, bypass keyword filtering (trust subreddit selection)
            enable_search: If True, run targeted search for service requests
        """
        super().__init__(keywords, rate_limit, days_filter)
        self.subreddits = subreddits
        self.skip_keyword_filter = skip_keyword_filter  # FIX: Store as instance variable
        self.enable_search = enable_search  # FIX: Store search flag

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
        Quick check if post could be a service inquiry (soft filter).
        Removes obvious non-inquiries without requiring keyword match.

        Returns:
            True if lead could be a service inquiry, False if obviously not
        """
        content_lower = lead.content.lower()
        title_lower = (lead.title or "").lower()
        full_text = f"{title_lower} {content_lower}"

        # EXCLUDE: Obvious non-inquiries
        exclude_patterns = [
            # News/announcements
            "just launched", "proud to announce", "we released",
            "new feature", "check out our", "introducing",

            # Self-promotion
            "i built", "i made", "i created", "my startup",
            "my company", "our product", "our platform",

            # Link spam
            "read more:", "full article:", "source:",

            # Questions to community (not service requests)
            "what do you think", "thoughts on", "anyone else",
            "does anyone else", "is it just me",

            # Educational/discussion
            "eli5", "explain like", "can someone explain",
            "what is", "what are", "how does"  # without business context
        ]

        # If contains exclude pattern, likely not inquiry
        if any(pattern in full_text for pattern in exclude_patterns):
            # EXCEPTION: If also has buying signal, keep it
            buying_signals = [
                "budget", "willing to pay", "looking for", "need help",
                "hire", "hiring", "seeking", "recommend"
            ]
            if not any(signal in full_text for signal in buying_signals):
                return False

        # INCLUDE: Clear service inquiry signals
        inquiry_signals = [
            # Direct requests
            "looking for", "need help", "need someone", "need a",
            "anyone recommend", "recommendations for",

            # Hiring
            "[hiring]", "[for hire]", "[task]",
            "hiring", "looking to hire",

            # Budget/payment
            "budget", "willing to pay", "can pay",

            # Problem statements
            "struggling with", "help with", "stuck on",

            # Evaluation
            "considering", "evaluating", "exploring options"
        ]

        # If has inquiry signal, definitely keep
        if any(signal in full_text for signal in inquiry_signals):
            return True

        # Default: Keep borderline cases (let LLM decide)
        # This soft filter only removes obvious non-inquiries
        return len(lead.content.split()) >= 15  # At least 15 words (substantive post)

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
        Scrape posts and comments from specified subreddits.

        Combines two scraping methods:
        1. Targeted search for high-intent service requests (if enable_search=True)
        2. Subreddit scraping for all posts in target communities

        Returns:
            Deduplicated list of leads
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

        # FIX (ISSUE #2): Targeted search for service requests (if enabled)
        if self.enable_search:
            try:
                search_leads = await self._search_reddit_for_service_requests()
                all_leads.extend(search_leads)
                if search_leads:
                    print(f"   🎯 Reddit Search: Found {len(search_leads)} targeted leads from search phrases")
            except Exception as e:
                print(f"   ⚠️ Reddit Search failed: {e}")
                # IMPROVED (ISSUE #4): Debug mode with traceback
                if settings.debug_mode:
                    traceback.print_exc()

        # Scrape all subreddits
        for subreddit_name in self.subreddits:
            try:
                leads = await self._scrape_subreddit(subreddit_name)
                all_leads.extend(leads)
            except Exception as e:
                # IMPROVED (ISSUE #4): More specific error message
                print(f"❌ Reddit: Error scraping r/{subreddit_name}: {e}")
                if settings.debug_mode:
                    traceback.print_exc()
                continue

        # FIX (ISSUE #2): Deduplicate by URL (search might find same posts as subreddit scraping)
        seen_urls = set()
        unique_leads = []
        for lead in all_leads:
            if lead.url not in seen_urls:
                seen_urls.add(lead.url)
                unique_leads.append(lead)

        if len(all_leads) != len(unique_leads):
            print(f"   🔄 Reddit: Deduplicated {len(all_leads)} → {len(unique_leads)} leads")

        return unique_leads

    async def _search_reddit_for_service_requests(self) -> list[Lead]:
        """
        Search Reddit for specific service request phrases.
        Targets high-intent leads asking for RWA/tokenization services.

        Returns:
            List of leads from targeted search
        """
        leads: list[Lead] = []

        # High-intent search phrases
        search_phrases = [
            "need help tokenizing",
            "looking for tokenization service",
            "best RWA platform",
            "real estate tokenization service",
            "need asset tokenization",
            "tokenization provider",
            "how to tokenize assets",
            "tokenization platform recommendation"
        ]

        # Get PRAW time filter
        time_filter = self._get_time_filter_for_praw()

        # Search across all subreddits
        try:
            for phrase in search_phrases:
                await self._apply_rate_limit()

                # Search Reddit with time filter
                try:
                    search_results = await asyncio.to_thread(
                        lambda: list(self.reddit.subreddit('all').search(
                            phrase,
                            time_filter=time_filter,
                            limit=20
                        ))
                    )
                except Exception as e:
                    # IMPROVED (ISSUE #4): Specific error for search phrase
                    print(f"⚠️ Reddit: Search failed for phrase '{phrase}': {e}")
                    if settings.debug_mode:
                        traceback.print_exc()
                    continue

                for submission in search_results:
                    await self._apply_rate_limit()

                    # Create lead from search result
                    try:
                        post_lead = self._create_lead_from_post(submission, submission.subreddit.display_name)
                        if post_lead:
                            # Mark as search-targeted lead
                            post_lead.metadata['search_phrase'] = phrase
                            post_lead.metadata['targeted_search'] = True
                            leads.append(post_lead)
                    except Exception as e:
                        # IMPROVED (ISSUE #4): Include post ID in error
                        print(f"⚠️ Reddit: Error processing search result {submission.id} for phrase '{phrase}': {e}")
                        if settings.debug_mode:
                            traceback.print_exc()
                        continue

                    # Also check comments on search results (high-engagement only)
                    if submission.score >= 20:
                        try:
                            await asyncio.to_thread(submission.comments.replace_more, limit=0)
                            all_comments = await asyncio.to_thread(submission.comments.list)

                            for comment in all_comments[:30]:
                                if isinstance(comment, Comment):
                                    comment_lead = self._create_lead_from_comment(
                                        comment,
                                        submission,
                                        submission.subreddit.display_name
                                    )
                                    if comment_lead:
                                        comment_lead.metadata['search_phrase'] = phrase
                                        comment_lead.metadata['targeted_search'] = True
                                        leads.append(comment_lead)
                        except Exception as e:
                            # IMPROVED (ISSUE #4): Specific error for comment processing
                            print(f"⚠️ Reddit: Error processing search comments for post {submission.id}: {e}")
                            if settings.debug_mode:
                                traceback.print_exc()
                            continue

        except Exception as e:
            # IMPROVED (ISSUE #4): General search error
            print(f"❌ Reddit: Error in targeted search: {e}")
            if settings.debug_mode:
                traceback.print_exc()

        return leads

    async def _scrape_subreddit(self, subreddit_name: str) -> list[Lead]:
        """
        Scrape a single subreddit for posts and comments.

        Args:
            subreddit_name: Name of subreddit (without r/ prefix)

        Returns:
            List of leads from this subreddit
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

                # Check post
                try:
                    post_lead = self._create_lead_from_post(submission, subreddit_name)
                    if post_lead:
                        leads.append(post_lead)
                        # DEBUG: Uncomment for lead creation tracking
                        # print(f"   DEBUG: Created lead from post {submission.id}, score={submission.score}")
                except Exception as e:
                    # IMPROVED (ISSUE #4): Include post ID and subreddit in error
                    print(f"⚠️ Reddit: Error processing post {submission.id} in r/{subreddit_name}: {e}")
                    if settings.debug_mode:
                        traceback.print_exc()
                    continue

                # OPTIMIZED: Minimal comment processing (posts > comments for service requests)
                # Only process comments on high-engagement posts in help-seeking subreddits
                HELP_SEEKING_SUBREDDITS = ['forhire', 'slavelabour', 'Jobs4Bitcoins', 'hire']
                is_help_subreddit = subreddit_name.lower() in HELP_SEEKING_SUBREDDITS

                if is_help_subreddit and submission.score >= 20:
                    comment_limit = 10  # Only top 10 comments (reduced from 20-50)
                elif submission.score >= 100:
                    comment_limit = 5   # Only top 5 for viral posts
                else:
                    comment_limit = 0   # Skip comments entirely (focus on posts)

                # DEBUG: Uncomment for comment fetching info
                # print(f"   DEBUG: Fetching {comment_limit} comments from post {submission.id}")

                # Check comments (skip if comment_limit is 0)
                if comment_limit > 0:
                    try:
                        # FIX (ISSUE #3): No additional rate limiting - PRAW handles this internally
                        # Wrap blocking PRAW operations in thread executor
                        await asyncio.to_thread(submission.comments.replace_more, limit=0)
                        all_comments = await asyncio.to_thread(submission.comments.list)

                        for comment in all_comments[:comment_limit]:
                            if isinstance(comment, Comment):
                                comment_lead = self._create_lead_from_comment(
                                    comment,
                                    submission,
                                    subreddit_name
                                )
                                if comment_lead:
                                    leads.append(comment_lead)
                    except Exception as e:
                        # IMPROVED (ISSUE #4): Specific error for comment fetching
                        print(f"⚠️ Reddit: Error fetching comments for post {submission.id}: {e}")
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

    def _create_lead_from_comment(
        self,
        comment: Comment,
        submission: Submission,
        subreddit_name: str
    ) -> Lead | None:
        """
        Create a Lead object from a Reddit comment.

        Args:
            comment: PRAW Comment object
            submission: Parent submission
            subreddit_name: Name of subreddit

        Returns:
            Lead object or None if creation fails
        """
        try:
            if not comment.body or comment.body in ['[deleted]', '[removed]']:
                return None

            # Check date filter
            comment_date = datetime.fromtimestamp(comment.created_utc)
            if not self._is_within_date_range(comment_date):
                return None

            return Lead(
                source='reddit',
                author=str(comment.author) if comment.author else '[deleted]',
                content=comment.body,
                timestamp=comment_date,
                url=f"https://reddit.com{comment.permalink}",
                title=submission.title,
                engagement_score=comment.score,
                subreddit=subreddit_name,
                metadata={
                    'comment_id': comment.id,
                    'post_id': submission.id,
                    'post_type': 'comment',
                    'parent_post_title': submission.title
                }
            )
        except Exception as e:
            # IMPROVED (ISSUE #4): Include comment ID if available
            comment_id = getattr(comment, 'id', 'unknown')
            print(f"⚠️ Reddit: Error creating lead from comment {comment_id}: {e}")
            if settings.debug_mode:
                traceback.print_exc()
            return None

    def __repr__(self) -> str:
        """String representation showing configuration."""
        # IMPROVED: Show new flags in repr
        return (
            f"RedditScraper("
            f"subreddits={len(self.subreddits)}, "
            f"keywords={len(self.keywords)}, "
            f"skip_keyword_filter={self.skip_keyword_filter}, "
            f"enable_search={self.enable_search}"
            f")"
        )
