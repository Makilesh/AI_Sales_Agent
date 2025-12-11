
import asyncio
import urllib.parse
from datetime import datetime
from typing import Optional

from apify_client import ApifyClient

from models.lead import Lead
from scrapers.base import BaseScraper


class LinkedInApifyScraper(BaseScraper):
    """Professional LinkedIn scraper for finding SERVICE INQUIRIES."""
    
    # ===================================================================
    # SERVICE TYPE CLASSIFICATION - Tag leads by industry/service type
    # ===================================================================
    SERVICE_CATEGORIES = {
        'RWA': [
            'real world asset', 'rwa', 'tokenization', 'tokenize', 
            'asset tokenization', 'real estate token', 'physical asset',
            'commodities', 'tokenized asset', 'on-chain asset'
        ],
        'Crypto': [
            'cryptocurrency', 'crypto', 'bitcoin', 'ethereum', 'defi',
            'decentralized finance', 'crypto exchange', 'crypto wallet',
            'crypto payment', 'crypto integration', 'web3', 'dapp'
        ],
        'Blockchain': [
            'blockchain', 'smart contract', 'distributed ledger', 'dlt',
            'blockchain development', 'blockchain solution', 'blockchain platform',
            'consensus', 'node', 'blockchain integration'
        ],
        'NFT': [
            'nft', 'non-fungible token', 'nft marketplace', 'nft collection',
            'digital collectible', 'nft platform', 'nft minting'
        ],
        'AI/ML': [
            'artificial intelligence', 'machine learning', 'ai solution',
            'ml model', 'deep learning', 'neural network', 'ai integration',
            'chatbot', 'ai automation', 'predictive analytics'
        ],
        'Fintech': [
            'fintech', 'financial technology', 'payment gateway', 'payment processing',
            'digital payment', 'banking solution', 'financial platform',
            'lending platform', 'investment platform'
        ],
        'Development': [
            'software development', 'app development', 'web development',
            'mobile app', 'custom solution', 'api integration',
            'system integration', 'platform development'
        ]
    }
    
    def __init__(
        self,
        apify_token: str,
        keywords: list[str],
        max_posts_per_keyword: int = 20,
        rate_limit: int = 10,  # requests per minute
        actor_id: str = "curious_coder/linkedin-post-search-scraper",
        linkedin_cookie: str = "",
        proxy_config: str = "",
        scrape_posts: bool = True,
        scrape_articles: bool = True,
        scrape_discussions: bool = True,
        scrape_comments: bool = True,
        scrape_reactions: bool = True,
        only_posts: bool = True,
        include_sponsored: bool = False,
        min_reactions: int = 0,
        max_total_leads: int = 200  # Global limit across all keywords
    ) -> None:
        """
        Initialize LinkedIn Apify scraper for SERVICE LEAD discovery.
        
        Args:
            apify_token: Apify API token
            keywords: Search keywords for LinkedIn posts (SERVICE-FOCUSED)
            max_posts_per_keyword: Maximum posts to fetch per keyword
            rate_limit: API requests per minute
            actor_id: Apify actor ID to use
            linkedin_cookie: LinkedIn li_at cookie (required by some actors)
            proxy_config: Proxy URL (optional, format: http://user:pass@host:port)
            scrape_posts: Include regular posts
            scrape_articles: Include LinkedIn articles
            scrape_discussions: Include discussion threads
            scrape_comments: Include post comments
            scrape_reactions: Include reaction data
            only_posts: Exclude company updates/ads
            include_sponsored: Include sponsored content
            min_reactions: Minimum reactions to consider
            max_total_leads: Global limit - stop scraping after this many total leads
        """
        super().__init__(keywords, rate_limit)
        self.apify_token = apify_token
        self.max_posts_per_keyword = max_posts_per_keyword
        self.max_total_leads = max_total_leads
        self.actor_id = actor_id
        self.linkedin_cookie = linkedin_cookie
        self.proxy_config = proxy_config
        self.scrape_posts = scrape_posts
        self.scrape_articles = scrape_articles
        self.scrape_discussions = scrape_discussions
        self.scrape_comments = scrape_comments
        self.scrape_reactions = scrape_reactions
        self.only_posts = only_posts
        self.include_sponsored = include_sponsored
        self.min_reactions = min_reactions
        
        # Initialize client first
        self.client = ApifyClient(apify_token)
        
        # Then validate
        if not self._validate_apify_token():
            raise ValueError("Invalid or missing Apify token")
    
    def _validate_apify_token(self) -> bool:
        """Validate that Apify token is present and formatted correctly."""
        if not self.apify_token:
            print("⚠️  Apify token not configured")
            return False
        
        if not self.apify_token.startswith('apify_api_'):
            print("⚠️  Apify token format invalid (should start with 'apify_api_')")
            return False
        
        # Test token by checking account info
        try:
            user = self.client.user().get()
            print(f"✓ Apify token valid (User: {user.get('username', 'Unknown')})")
        except Exception as e:
            print(f"⚠️  Apify token test failed: {e}")
            return False
        
        return True
    
    def _classify_service_type(self, text: str) -> list[str]:
        """
        Classify lead by service category (RWA, Crypto, AI, etc.).
        
        Returns list of matching categories.
        """
        if not text:
            return []
        
        text_lower = text.lower()
        categories = []
        
        for category, keywords in self.SERVICE_CATEGORIES.items():
            if any(keyword.lower() in text_lower for keyword in keywords):
                categories.append(category)
        
        return categories if categories else ['General']
    
    async def scrape(self) -> list[Lead]:
        """Scrape LinkedIn posts via Apify for all keywords with global rate limit."""
        all_leads: list[Lead] = []
        seen_urls = set()  # Track URLs to avoid duplicates
        
        print(f"🔍 Starting LinkedIn scraping via Apify")
        print(f"   • Max posts per keyword: {self.max_posts_per_keyword}")
        print(f"   • Global lead limit: {self.max_total_leads}")
        print(f"   • Keywords to search: {len(self.keywords)}")
        print(f"🎯 Focus: SERVICE INQUIRIES")
        print("   Looking for: People explicitly asking for our services (not just discussing topics)")
        
        for idx, keyword in enumerate(self.keywords, 1):
            # Check global limit BEFORE scraping each keyword
            if len(all_leads) >= self.max_total_leads:
                print(f"\n⚠️  Global lead limit reached ({self.max_total_leads} leads)")
                print(f"   Stopping early (scraped {idx-1}/{len(self.keywords)} keywords)")
                print(f"   💰 Credit savings: Skipped {len(self.keywords) - idx + 1} keywords")
                break
            
            try:
                # Calculate remaining budget for this keyword
                remaining_budget = self.max_total_leads - len(all_leads)
                posts_to_fetch = min(self.max_posts_per_keyword, remaining_budget)
                
                if posts_to_fetch <= 0:
                    break
                
                print(f"\n  [{idx}/{len(self.keywords)}] Keyword: '{keyword}' (budget: {posts_to_fetch} posts)")
                leads = await self._scrape_keyword(keyword, posts_to_fetch)
                
                # Add service classification and filter duplicates
                unique_leads = []
                for lead in leads:
                    if lead.url not in seen_urls:
                        service_types = self._classify_service_type(lead.content + " " + (lead.title or ""))
                        lead.metadata['service_types'] = service_types
                        lead.metadata['service_inquiry'] = True
                        
                        unique_leads.append(lead)
                        seen_urls.add(lead.url)
                
                all_leads.extend(unique_leads)
                duplicates = len(leads) - len(unique_leads)
                if duplicates > 0:
                    print(f"  ✓ Extracted {len(unique_leads)} service leads ({duplicates} duplicates removed) | Total: {len(all_leads)}/{self.max_total_leads}")
                else:
                    print(f"  ✓ Extracted {len(unique_leads)} service leads | Total: {len(all_leads)}/{self.max_total_leads}")
            except Exception as e:
                print(f"  ✗ Error scraping '{keyword}': {e}")
        
        print(f"\n✅ Scraping complete: {len(all_leads)} LinkedIn service leads collected")
        return all_leads
    
    async def _scrape_keyword(self, keyword: str, posts_limit: int = None) -> list[Lead]:
        """Scrape LinkedIn posts for a single keyword via Apify."""
        leads: list[Lead] = []
        
        # Use custom limit if provided (for rate limiting), otherwise use default
        effective_limit = posts_limit if posts_limit is not None else self.max_posts_per_keyword
        
        try:
            # Build LinkedIn search URL for the keyword
            import urllib.parse
            
            # For multi-word keywords, try just the most important word
            # LinkedIn's search works better with simple terms
            keyword_parts = keyword.split()
            if len(keyword_parts) > 2:
                # Use the most distinctive word (usually the last substantive word)
                simple_keyword = keyword_parts[-1] if keyword_parts[-1] not in ['developer', 'consultant', 'engineer', 'project', 'platform', 'solution'] else keyword_parts[0]
                print(f"     ℹ️  Simplifying '{keyword}' → '{simple_keyword}' for LinkedIn search")
                search_term = simple_keyword
            else:
                search_term = keyword
            
            encoded_keyword = urllib.parse.quote(search_term)
            search_url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_keyword}"
            
            # Detect actor type and configure input accordingly
            if 'apify/linkedin-posts-scraper' in self.actor_id:
                # apify/linkedin-posts-scraper (RECOMMENDED - most reliable)
                run_input = {
                    'startUrls': [{'url': search_url}],
                    'resultsLimit': effective_limit
                }
            elif 'supreme_coder' in self.actor_id:
                # supreme_coder/linkedin-post actor
                run_input = {
                    'urls': [search_url],
                    'limit': effective_limit
                }
            elif 'curious_coder' in self.actor_id:
                # curious_coder actor - requires cookies
                if not self.linkedin_cookie:
                    print(f"     ⚠️  Warning: curious_coder actor requires LinkedIn cookie (li_at)")
                run_input = {
                    'urls': [search_url],
                    'maxPosts': effective_limit,
                    'cookie': [{
                        'name': 'li_at',
                        'value': self.linkedin_cookie,
                        'domain': '.linkedin.com'
                    }] if self.linkedin_cookie else [],
                    'userAgent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'proxy': {
                        'useApifyProxy': True
                    } if not self.proxy_config else {
                        'proxyUrls': [self.proxy_config]
                    }
                }
            else:
                # Generic fallback
                run_input = {
                    'startUrls': [{'url': search_url}],
                    'maxItems': effective_limit
                }
            
            print(f"     → Running Apify actor ({self.actor_id})...")
            if 'supreme_coder' in self.actor_id or 'apify/linkedin-posts-scraper' in self.actor_id:
                print(f"        • No cookies required ✓")
            else:
                print(f"        • Using LinkedIn authentication")
            print(f"        • Fetching up to {effective_limit} posts")
            print(f"        • Search URL: {search_url}")
            print(f"        • Actor input: {run_input}")
            
            # Run Apify actor (blocking call, wrap in thread)
            try:
                run = await asyncio.to_thread(
                    self.client.actor(self.actor_id).call,
                    run_input=run_input
                )
                print(f"     → Actor run completed: {run.get('status', 'unknown')}")
            except Exception as actor_error:
                print(f"     ❌ Actor execution failed: {actor_error}")
                print(f"        Tip: Check if actor '{self.actor_id}' exists at https://console.apify.com/")
                raise
            
            # Fetch results from dataset
            print(f"     → Fetching results from dataset ({run.get('defaultDatasetId', 'unknown')})...")
            dataset_items = await asyncio.to_thread(
                self.client.dataset(run['defaultDatasetId']).list_items
            )
            
            # Handle different response formats
            if hasattr(dataset_items, 'items'):
                items = dataset_items.items
            elif isinstance(dataset_items, dict):
                items = dataset_items.get('items', [])
            else:
                items = dataset_items
            
            print(f"     → Found {len(items)} raw items from Apify")
            
            if len(items) == 0:
                print(f"     ⚠️  No items returned from Apify actor")
                print(f"        Possible reasons:")
                print(f"        1. Keyword '{keyword}' has no matching LinkedIn posts")
                print(f"        2. Actor configuration issue (check input format)")
                print(f"        3. LinkedIn rate limiting or blocking")
                print(f"        4. Apify actor may require authentication")
                print(f"        5. Try simpler keywords (single words work best)")
                print(f"     💡 Debug: Check run at https://console.apify.com/actors/runs/{run.get('id', 'unknown')}")
                return []
            
            # Parse each item
            for item in items:
                try:
                    # Filter by content type
                    item_type = item.get('type', 'post').lower()
                    
                    if item_type == 'post' and not self.scrape_posts:
                        continue
                    if item_type == 'article' and not self.scrape_articles:
                        continue
                    if item_type in ['discussion', 'thread'] and not self.scrape_discussions:
                        continue
                    
                    # Filter by reaction count
                    reactions_total = item.get('reactions', {}).get('total', 0) if isinstance(item.get('reactions'), dict) else 0
                    likes = item.get('likes', 0) or 0
                    total_reactions = reactions_total + likes
                    
                    if total_reactions < self.min_reactions:
                        continue
                    
                    lead = self._create_lead_from_apify_item(item, keyword)
                    if lead:
                        leads.append(lead)
                except Exception as e:
                    continue
        
        except Exception as e:
            print(f"     ⚠️  Apify API error: {e}")
            return []
        
        return leads
    
    def _create_lead_from_apify_item(self, item: dict, keyword: str) -> Optional[Lead]:
        """Create Lead object from Apify response item."""
        try:
            # Extract author
            author = item.get('authorName', 'LinkedIn User')
            
            # Extract content (try multiple fields)
            content = (
                item.get('text', '') or 
                item.get('commentary', '') or 
                item.get('description', '')
            )
            
            if not content or len(content.strip()) < 10:
                return None
            
            # Extract timestamp
            timestamp_str = item.get('postedAt') or item.get('createdAt')
            if timestamp_str:
                try:
                    # Handle ISO format with timezone
                    if timestamp_str.endswith('Z'):
                        timestamp_str = timestamp_str[:-1] + '+00:00'
                    timestamp = datetime.fromisoformat(timestamp_str)
                except Exception:
                    timestamp = datetime.now()
            else:
                timestamp = datetime.now()
            
            # Extract URL
            url = item.get('postUrl', '') or item.get('url', '')
            if not url:
                # Fallback: construct from post ID if available
                post_id = item.get('postId', '')
                if post_id:
                    url = f"https://www.linkedin.com/feed/update/{post_id}"
                else:
                    return None
            
            # Extract title (may be None for comments)
            title = item.get('title') or item.get('headline')
            
            # Calculate engagement score
            likes = item.get('likes', 0) or 0
            reactions_total = item.get('reactions', {}).get('total', 0) if isinstance(item.get('reactions'), dict) else 0
            engagement_score = likes + reactions_total
            
            # Determine post type
            linkedin_post_type = item.get('type', 'post')  # 'post', 'article', 'video', 'comment'
            
            # Build metadata
            metadata = {
                'search_query': keyword,
                'post_id': item.get('postId'),
                'author_profile': item.get('authorProfileUrl'),
                'comment_count': item.get('commentsCount', 0),
                'via_apify': True,
                'actor': self.actor_id
            }
            
            return Lead(
                source='linkedin',
                author=author,
                content=content,
                timestamp=timestamp,
                url=url,
                title=title,
                engagement_score=engagement_score,
                linkedin_post_type=linkedin_post_type,
                metadata=metadata
            )
        
        except Exception as e:
            print(f"    ⚠️  Error creating lead from item: {e}")
            return None
    
    def __repr__(self) -> str:
        content_types = []
        if self.scrape_posts:
            content_types.append('posts')
        if self.scrape_articles:
            content_types.append('articles')
        if self.scrape_discussions:
            content_types.append('discussions')
        
        return (
            f"LinkedInApifyScraper("
            f"keywords={len(self.keywords)}, "
            f"max_posts={self.max_posts_per_keyword}, "
            f"max_total={self.max_total_leads}, "
            f"actor={self.actor_id})"
        )
