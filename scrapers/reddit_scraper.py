
import asyncio
from datetime import datetime, timedelta

import praw
from praw.models import Submission, Comment

from models.lead import Lead
from scrapers.base import BaseScraper


class RedditScraper(BaseScraper):
    """Scraper for Reddit posts and comments."""
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        keywords: list[str],
        subreddits: list[str],
        rate_limit: int = 100,
        days_filter: int = 30
    ) -> None:
        super().__init__(keywords, rate_limit, days_filter)
        self.subreddits = subreddits
        self.skip_keyword_filter = True  # Reddit uses help-seeking subreddits, bypass keyword filter
        
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
        Override parent's keyword filtering for Reddit.
        
        Reddit uses help-seeking subreddits, so we trust the subreddit selection
        and let ALL posts through (LLM will filter for service match).
        """
        print(f"   ℹ️ Reddit: Keyword filter disabled (trusting help-seeking subreddits)")
        return leads  # Return all leads, no keyword filter
    
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
        """Scrape posts and comments from specified subreddits."""
        all_leads: list[Lead] = []
        
        # Print time filter info
        if self.days_filter > 0:
            cutoff_date = datetime.now() - timedelta(days=self.days_filter)
            time_filter = self._get_time_filter_for_praw()
            print(f"   🕒 Reddit: Filtering posts from last {self.days_filter} days (PRAW filter: '{time_filter}')")
            print(f"   📅 Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M')}")
        else:
            print(f"   ℹ️ Reddit: No time filter (fetching all posts)")
        
        # Scrape all subreddits with multi-feed approach
        for subreddit_name in self.subreddits:
            try:
                leads = await self._scrape_subreddit(subreddit_name)
                all_leads.extend(leads)
            except Exception as e:
                print(f"Error scraping r/{subreddit_name}: {e}")
                continue
        
        return all_leads
    
    async def _search_reddit_for_service_requests(self) -> list[Lead]:
        """
        Search Reddit for specific service request phrases.
        Targets high-intent leads asking for RWA/tokenization services.
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
                search_results = await asyncio.to_thread(
                    lambda: list(self.reddit.subreddit('all').search(
                        phrase, 
                        time_filter=time_filter,
                        limit=20
                    ))
                )
                
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
                            post_lead.metadata['search_phrase'] = phrase
                            post_lead.metadata['targeted_search'] = True
                            leads.append(post_lead)
                    except Exception as e:
                        print(f"Error processing search result {submission.id}: {e}")
                        continue
                    
                    # Also check comments on search results (high-engagement only)
                    if submission.score >= 20:
                        try:
                            await self._apply_rate_limit()
                            await asyncio.to_thread(submission.comments.replace_more, limit=0)
                            await self._apply_rate_limit()
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
                            await self._apply_rate_limit()
                            await asyncio.to_thread(submission.comments.replace_more, limit=0)
                            await self._apply_rate_limit()
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
                            print(f"Error processing search comments for {submission.id}: {e}")
                            continue
                            print(f"Error processing search comments for {submission.id}: {e}")
                            continue
            
            if leads:
                print(f"   🎯 Reddit Search: Found {len(leads)} targeted leads from search phrases")
                
        except Exception as e:
            print(f"Error in Reddit search: {e}")
        
        return leads
    
    async def _scrape_subreddit(self, subreddit_name: str) -> list[Lead]:
        """Scrape a single subreddit for posts and comments."""
        leads: list[Lead] = []
        
        try:
            # Wrap PRAW call in thread executor for true async
            subreddit = await asyncio.to_thread(self.reddit.subreddit, subreddit_name)
            
            # Get PRAW time filter
            time_filter = self._get_time_filter_for_praw()
            
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
            
            # Fetch posts with smart limits based on time filter
            if self.days_filter <= 1:
                # Last 24 hours: new posts are most relevant
                new_posts = await asyncio.to_thread(lambda: fetch_with_cutoff(subreddit.new(limit=200), 80))
                hot_posts = await asyncio.to_thread(lambda: fetch_with_cutoff(subreddit.hot(limit=100), 40))
                top_posts = await asyncio.to_thread(lambda: list(subreddit.top(time_filter='day', limit=30)))
            elif self.days_filter <= 7:
                # Last week: balanced approach
                new_posts = await asyncio.to_thread(lambda: fetch_with_cutoff(subreddit.new(limit=150), 50))
                hot_posts = await asyncio.to_thread(lambda: fetch_with_cutoff(subreddit.hot(limit=80), 30))
                top_posts = await asyncio.to_thread(lambda: list(subreddit.top(time_filter='week', limit=50)))
            elif self.days_filter <= 30:
                # Last month: focus on top posts
                new_posts = await asyncio.to_thread(lambda: fetch_with_cutoff(subreddit.new(limit=100), 30))
                hot_posts = await asyncio.to_thread(lambda: fetch_with_cutoff(subreddit.hot(limit=60), 20))
                top_posts = await asyncio.to_thread(lambda: list(subreddit.top(time_filter='month', limit=60)))
            else:
                # Longer periods or no filter: standard approach
                new_posts = await asyncio.to_thread(lambda: list(subreddit.new(limit=50)))
                hot_posts = await asyncio.to_thread(lambda: list(subreddit.hot(limit=50)))
                top_week = await asyncio.to_thread(lambda: list(subreddit.top(time_filter='week', limit=30)))
                top_month = await asyncio.to_thread(lambda: list(subreddit.top(time_filter=time_filter, limit=40)))
                top_posts = top_week + top_month
            
            # Combine and deduplicate (all posts already filtered by date)
            all_posts = {post.id: post for post in hot_posts + new_posts + top_posts}.values()
            posts_to_process = list(all_posts)
            
            print(f"   📊 r/{subreddit_name}: Processing {len(posts_to_process)}/{len(all_posts)} posts within time range")
            
            for submission in posts_to_process:
                await self._apply_rate_limit()
                
                # Check post
                try:
                    post_lead = self._create_lead_from_post(submission, subreddit_name)
                    if post_lead:
                        leads.append(post_lead)
                except Exception as e:
                    print(f"Error processing post {submission.id}: {e}")
                    continue
                
                # Dynamic comment depth based on engagement
                # High-engagement posts (score ≥50) get more comments checked
                comment_limit = 50 if submission.score >= 50 else 20
                
                # Check comments
                try:
                    # Apply rate limit before fetching comments
                    await self._apply_rate_limit()
                    # Wrap blocking PRAW operations in thread executor
                    await asyncio.to_thread(submission.comments.replace_more, limit=0)
                    await self._apply_rate_limit()
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
                    print(f"Error processing comments for {submission.id}: {e}")
                    continue
        
        except Exception as e:
            print(f"Error accessing subreddit r/{subreddit_name}: {e}")
        
        return leads
    
    def _create_lead_from_post(self, submission: Submission, subreddit_name: str) -> Lead | None:
        """Create a Lead object from a Reddit post."""
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
            print(f"Error creating lead from post: {e}")
            return None
    
    def _create_lead_from_comment(
        self, 
        comment: Comment, 
        submission: Submission,
        subreddit_name: str
    ) -> Lead | None:
        """Create a Lead object from a Reddit comment."""
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
            print(f"Error creating lead from comment: {e}")
            return None
    
    def __repr__(self) -> str:
        return f"RedditScraper(subreddits={len(self.subreddits)}, keywords={len(self.keywords)})"
