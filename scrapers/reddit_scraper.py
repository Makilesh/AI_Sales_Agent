
import asyncio
from datetime import datetime

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
        print(f"   � Reddit: Keyword filter disabled (trusting help-seeking subreddits)")
        return leads  # Return all leads, no keyword filter
    
    async def scrape(self) -> list[Lead]:
        """Scrape posts and comments from specified subreddits."""
        all_leads: list[Lead] = []
        
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
        
        # Search across all subreddits
        try:
            for phrase in search_phrases:
                await self._apply_rate_limit()
                
                # Search Reddit with time filter (last month)
                search_results = await asyncio.to_thread(
                    lambda: list(self.reddit.subreddit('all').search(
                        phrase, 
                        time_filter='month',
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
                        except Exception as e:
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
            
            # Scrape from multiple feeds for maximum coverage
            # Hot posts (current trending)
            hot_posts = await asyncio.to_thread(lambda: list(subreddit.hot(limit=50)))
            # New posts (recent activity)
            new_posts = await asyncio.to_thread(lambda: list(subreddit.new(limit=50)))
            # Top posts from the past week (high-quality content)
            top_week_posts = await asyncio.to_thread(lambda: list(subreddit.top(time_filter='week', limit=30)))
            # Top posts from the past month (more high-quality content)
            top_month_posts = await asyncio.to_thread(lambda: list(subreddit.top(time_filter='month', limit=20)))
            
            # Combine and deduplicate
            all_posts = {post.id: post for post in hot_posts + new_posts + top_week_posts + top_month_posts}.values()
            
            for submission in all_posts:
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
