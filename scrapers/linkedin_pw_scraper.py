"""
LinkedIn Playwright Scraper - Production-ready browser automation scraper.

This scraper uses Playwright for authenticated LinkedIn scraping with anti-detection measures.
Combines the robust features of linkedin_apify_scraper with browser automation reliability.
"""

import asyncio
import random
import re
from datetime import datetime, timedelta
from typing import Optional

from playwright.async_api import async_playwright, Page, Browser, BrowserContext, TimeoutError as PlaywrightTimeout

from models.lead import Lead
from scrapers.base import BaseScraper


class LinkedInPlaywrightScraper(BaseScraper):
    """
    Production LinkedIn scraper using Playwright browser automation.
    
    Features:
    - Authenticated scraping with li_at cookie
    - Anti-detection measures (stealth mode, random delays, user agent rotation)
    - Service categorization (RWA, Crypto, Blockchain, AI/ML)
    - Pagination support with scroll/load more
    - Rate limiting and error handling
    - Deduplication by URL
    """
    
    # Service categories for classification
    SERVICE_CATEGORIES = {
        'RWA': ['tokenization', 'real world asset', 'rwa', 'asset tokenization', 'security token', 'sto', 
                'fractional ownership', 'asset backed', 'token offering'],
        'Crypto': ['cryptocurrency', 'crypto', 'bitcoin', 'ethereum', 'altcoin', 'trading platform',
                   'crypto exchange', 'digital currency', 'crypto wallet'],
        'Blockchain': ['blockchain', 'distributed ledger', 'consensus', 'web3', 'dlt',
                       'blockchain development', 'blockchain infrastructure', 'node operator'],
        'DeFi': ['defi', 'decentralized finance', 'liquidity', 'yield farming', 'dex',
                 'lending protocol', 'staking', 'liquidity pool', 'amm'],
        'NFT': ['nft', 'non-fungible token', 'digital art', 'collectible', 'nft marketplace',
                'metaverse', 'digital collectibles'],
        'Smart Contract': ['smart contract', 'solidity', 'ethereum contract', 'web3 development',
                           'contract audit', 'dapp', 'decentralized application'],
        'AI/ML': ['artificial intelligence', 'machine learning', 'ai', 'ml', 'deep learning',
                  'neural network', 'nlp', 'computer vision', 'ai model']
    }
    
    # Desktop user agents for rotation
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    ]
    
    # Viewport sizes for randomization
    VIEWPORTS = [
        {'width': 1920, 'height': 1080},
        {'width': 1366, 'height': 768},
        {'width': 1440, 'height': 900},
        {'width': 1536, 'height': 864},
        {'width': 1680, 'height': 1050},
    ]
    
    # Geographic locations for randomization
    LOCATIONS = [
        {'city': 'New York', 'timezone': 'America/New_York', 'longitude': -74.0060, 'latitude': 40.7128},
        {'city': 'London', 'timezone': 'Europe/London', 'longitude': -0.1278, 'latitude': 51.5074},
        {'city': 'Singapore', 'timezone': 'Asia/Singapore', 'longitude': 103.8198, 'latitude': 1.3521},
        {'city': 'Tokyo', 'timezone': 'Asia/Tokyo', 'longitude': 139.6917, 'latitude': 35.6895},
        {'city': 'Sydney', 'timezone': 'Australia/Sydney', 'longitude': 151.2093, 'latitude': -33.8688},
        {'city': 'San Francisco', 'timezone': 'America/Los_Angeles', 'longitude': -122.4194, 'latitude': 37.7749},
        {'city': 'Berlin', 'timezone': 'Europe/Berlin', 'longitude': 13.4050, 'latitude': 52.5200},
    ]
    
    def __init__(
        self,
        linkedin_cookie: str,
        keywords: list[str],
        max_posts_per_keyword: int = 50,
        max_total_leads: int = 200,
        rate_limit: int = 10,  # requests per minute
        headless: bool = True,
        days_filter: int = 30,
        proxy: str | None = None
    ) -> None:
        """
        Initialize LinkedIn Playwright scraper.
        
        Args:
            linkedin_cookie: li_at cookie value for authentication
            keywords: List of search keywords
            max_posts_per_keyword: Maximum posts to scrape per keyword
            max_total_leads: Global limit for total leads
            rate_limit: Requests per minute (for rate limiting)
            headless: Run browser in headless mode
            days_filter: Filter posts from last N days
            proxy: Optional proxy server (format: "http://host:port" or "http://user:pass@host:port")
        """
        super().__init__(keywords, rate_limit, days_filter=days_filter)
        self.linkedin_cookie = linkedin_cookie
        self.max_posts_per_keyword = max_posts_per_keyword
        self.max_total_leads = max_total_leads
        self.headless = headless
        self.days_filter = days_filter
        self.proxy = proxy
        
        # Playwright objects (initialized in _setup_browser)
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        
        # Tracking
        self.seen_urls = set()
        self.request_count = 0
        self.last_request_time = datetime.now()
        
    async def _setup_browser(self) -> None:
        """Initialize Playwright browser with stealth settings and authentication."""
        try:
            print("🚀 Initializing Playwright browser...")
            
            self.playwright = await async_playwright().start()
            
            # Random user agent, viewport, and location
            user_agent = random.choice(self.USER_AGENTS)
            viewport = random.choice(self.VIEWPORTS)
            location = random.choice(self.LOCATIONS)
            
            print(f"   • User Agent: {user_agent[:50]}...")
            print(f"   • Viewport: {viewport['width']}x{viewport['height']}")
            print(f"   • Location: {location['city']} ({location['timezone']})")
            print(f"   • Headless: {self.headless}")
            if self.proxy:
                print(f"   • Proxy: {self.proxy.split('@')[-1] if '@' in self.proxy else self.proxy}")
            
            # Launch browser with stealth settings
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-web-security',
                    '--disable-features=IsolateOrigins,site-per-process',
                ]
            )
            
            # Build context options
            context_options = {
                'user_agent': user_agent,
                'viewport': viewport,
                'locale': 'en-US',
                'timezone_id': location['timezone'],
                'permissions': ['geolocation'],
                'geolocation': {
                    'longitude': location['longitude'], 
                    'latitude': location['latitude']
                },
                'extra_http_headers': {
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                }
            }
            
            # Add proxy if provided
            if self.proxy:
                context_options['proxy'] = {'server': self.proxy}
            
            # Create context with cookie and stealth settings
            self.context = await self.browser.new_context(**context_options)
            
            # Add LinkedIn authentication cookie
            await self.context.add_cookies([{
                'name': 'li_at',
                'value': self.linkedin_cookie,
                'domain': '.linkedin.com',
                'path': '/',
                'httpOnly': True,
                'secure': True,
                'sameSite': 'None'
            }])
            
            # Create page
            self.page = await self.context.new_page()
            
            # Apply stealth measures
            await self._apply_stealth(self.page)
            
            # Verify authentication by navigating to LinkedIn
            print("🔐 Verifying authentication...")
            await self.page.goto('https://www.linkedin.com/feed/', wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(3)
            
            # Check if we're logged in (look for profile elements)
            current_url = self.page.url
            if 'authwall' in current_url or 'login' in current_url:
                raise Exception("Authentication failed - redirected to login page. Check your li_at cookie.")
            
            print("✅ Browser initialized and authenticated successfully")
            
        except Exception as e:
            print(f"❌ Failed to initialize browser: {e}")
            await self.cleanup()
            raise
    
    async def _apply_stealth(self, page: Page) -> None:
        """Apply anti-detection measures to the page."""
        # Override navigator.webdriver
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        # Override plugins and languages
        await page.add_init_script("""
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
        """)
        
        # Override chrome object
        await page.add_init_script("""
            window.chrome = {
                runtime: {}
            };
        """)
        
        # Override permissions
        await page.add_init_script("""
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Reflect.get(Notification, 'permission') }) :
                    originalQuery(parameters)
            );
        """)
    
    async def _apply_rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        # Calculate time since last request
        time_since_last = (datetime.now() - self.last_request_time).total_seconds()
        
        # Calculate minimum delay (60 seconds / rate_limit requests per minute)
        min_delay = 60.0 / self.rate_limit
        
        # Add random human-like delay (5-10 seconds)
        human_delay = random.uniform(5.0, 10.0)
        total_delay = max(min_delay, human_delay)
        
        if time_since_last < total_delay:
            wait_time = total_delay - time_since_last
            await asyncio.sleep(wait_time)
        
        self.last_request_time = datetime.now()
        self.request_count += 1
    
    async def _random_mouse_movement(self) -> None:
        """Simulate random mouse movements for anti-detection."""
        if not self.page:
            return
        
        try:
            viewport = self.page.viewport_size
            if viewport:
                x = random.randint(100, viewport['width'] - 100)
                y = random.randint(100, viewport['height'] - 100)
                await self.page.mouse.move(x, y)
                await asyncio.sleep(random.uniform(0.1, 0.3))
        except Exception:
            pass  # Ignore mouse movement errors
    
    async def _human_like_scroll(self) -> None:
        """Simulate human-like scrolling behavior."""
        if not self.page:
            return
        
        try:
            # Random scroll distance
            scroll_distance = random.randint(300, 800)
            await self.page.evaluate(f'window.scrollBy(0, {scroll_distance})')
            await asyncio.sleep(random.uniform(0.5, 1.5))
        except Exception:
            pass  # Ignore scroll errors
    
    def _parse_relative_time(self, time_text: str) -> datetime:
        """
        Parse LinkedIn's relative time format (e.g., '2h ago', '3d ago', '1w ago').
        
        Args:
            time_text: Relative time string
            
        Returns:
            Approximate datetime
        """
        if not time_text:
            return datetime.now()
        
        time_text_lower = time_text.lower().strip()
        now = datetime.now()
        
        # Handle patterns like "2h", "3d", "1w", "2mo"
        match = re.search(r'(\d+)\s*(s|m|h|d|w|mo|y)', time_text_lower)
        
        if not match:
            # Try with "ago" suffix
            match = re.search(r'(\d+)\s*(second|minute|hour|day|week|month|year)s?\s*ago', time_text_lower)
            if match:
                amount = int(match.group(1))
                unit = match.group(2)[0]  # First letter
            else:
                return now
        else:
            amount = int(match.group(1))
            unit = match.group(2)
        
        # Convert to datetime
        if unit in ['s', 'second']:
            return now - timedelta(seconds=amount)
        elif unit in ['m', 'minute']:
            return now - timedelta(minutes=amount)
        elif unit in ['h', 'hour']:
            return now - timedelta(hours=amount)
        elif unit in ['d', 'day']:
            return now - timedelta(days=amount)
        elif unit in ['w', 'week']:
            return now - timedelta(weeks=amount)
        elif unit in ['mo', 'month']:
            return now - timedelta(days=amount * 30)
        elif unit in ['y', 'year']:
            return now - timedelta(days=amount * 365)
        
        return now
    
    def _classify_service_type(self, text: str) -> list[str]:
        """
        Classify lead by service category.
        
        Args:
            text: Post content to classify
            
        Returns:
            List of matching service categories
        """
        if not text:
            return ['General']
        
        text_lower = text.lower()
        categories = []
        
        for category, keywords in self.SERVICE_CATEGORIES.items():
            if any(keyword.lower() in text_lower for keyword in keywords):
                categories.append(category)
        
        return categories if categories else ['General']
    
    async def _extract_post_data(self, post_element, keyword: str, index: int) -> Optional[Lead]:
        """
        Extract data from a single LinkedIn post element.
        
        Args:
            post_element: Playwright element handle for the post
            keyword: Search keyword used
            index: Position in search results
            
        Returns:
            Lead object or None if extraction fails
        """
        try:
            # Extract author name
            author = "LinkedIn User"
            try:
                author_elem = await post_element.query_selector('.update-components-actor__name, .feed-shared-actor__name, [data-test-component="actor-name"]')
                if author_elem:
                    author = await author_elem.inner_text()
                    author = author.strip()
            except Exception:
                pass
            
            # Extract author profile URL
            author_url = ""
            try:
                author_link = await post_element.query_selector('.update-components-actor__meta-link, .app-aware-link[href*="/in/"]')
                if author_link:
                    author_url = await author_link.get_attribute('href')
                    if author_url and not author_url.startswith('http'):
                        author_url = f"https://www.linkedin.com{author_url}"
            except Exception:
                pass
            
            # Extract post content
            content = ""
            try:
                content_elem = await post_element.query_selector('.update-components-text, .feed-shared-update-v2__description, .feed-shared-text')
                if content_elem:
                    content = await content_elem.inner_text()
                    content = content.strip()
                    
                    # Handle "see more" - try to expand with improved reliability
                    see_more = await post_element.query_selector('.feed-shared-inline-show-more-text__see-more-less-toggle, .see-more, button[aria-label*="see more"]')
                    if see_more:
                        try:
                            # Try regular click with force
                            await see_more.click(force=True, timeout=2000)
                            await asyncio.sleep(0.8)  # Wait for expansion
                            content_elem = await post_element.query_selector('.update-components-text, .feed-shared-update-v2__description')
                            if content_elem:
                                content = await content_elem.inner_text()
                                content = content.strip()
                        except Exception as e:
                            # Fallback: try bounding box click
                            try:
                                box = await see_more.bounding_box()
                                if box:
                                    await self.page.mouse.click(
                                        box['x'] + box['width'] / 2,
                                        box['y'] + box['height'] / 2
                                    )
                                    await asyncio.sleep(0.8)
                                    content_elem = await post_element.query_selector('.update-components-text, .feed-shared-update-v2__description')
                                    if content_elem:
                                        content = await content_elem.inner_text()
                                        content = content.strip()
                            except Exception:
                                pass  # Keep truncated content
            except Exception:
                pass
            
            # Extract post URL
            post_url = ""
            try:
                url_elem = await post_element.query_selector('a[href*="/feed/update/"], a[href*="/posts/"]')
                if url_elem:
                    post_url = await url_elem.get_attribute('href')
                    if post_url:
                        # Clean URL
                        if '?' in post_url:
                            post_url = post_url.split('?')[0]
                        if not post_url.startswith('http'):
                            post_url = f"https://www.linkedin.com{post_url}"
            except Exception:
                pass
            
            # Skip if duplicate
            if post_url in self.seen_urls:
                return None
            
            # Extract timestamp
            timestamp = datetime.now()
            try:
                time_elem = await post_element.query_selector('.update-components-actor__sub-description time, .feed-shared-actor__sub-description time, time')
                if time_elem:
                    time_text = await time_elem.inner_text()
                    timestamp = self._parse_relative_time(time_text)
            except Exception:
                pass
            
            # Check date filter
            if self.days_filter > 0:
                lead_age_days = (datetime.now() - timestamp).days
                if lead_age_days > self.days_filter:
                    return None  # Too old
            
            # Extract engagement
            engagement_score = 0
            try:
                # Look for reactions/likes count
                reaction_elem = await post_element.query_selector('.social-details-social-counts__reactions-count, [aria-label*="reaction"]')
                if reaction_elem:
                    reaction_text = await reaction_elem.inner_text()
                    numbers = re.findall(r'\d+', reaction_text)
                    if numbers:
                        engagement_score = int(numbers[0])
            except Exception:
                pass
            
            # Extract post type
            post_type = 'post'
            try:
                # Check for article, video, etc.
                if await post_element.query_selector('[data-test-component="article"]'):
                    post_type = 'article'
                elif await post_element.query_selector('video, [data-test-component="video"]'):
                    post_type = 'video'
            except Exception:
                pass
            
            # Validate content
            if not content or len(content) < 20:
                return None
            
            if not post_url:
                return None
            
            # Classify service type
            service_types = self._classify_service_type(content)
            
            # Create lead
            lead = Lead(
                source='linkedin',
                author=author,
                content=content[:1000],  # Limit content length
                timestamp=timestamp,
                url=post_url,
                title=content[:100],  # First 100 chars as title
                engagement_score=engagement_score,
                linkedin_post_type=post_type,
                metadata={
                    'search_query': keyword,
                    'result_position': index,
                    'service_types': service_types,
                    'service_inquiry': True,  # Assume all scraped posts are inquiries
                    'via_playwright': True,
                    'author_url': author_url,
                    'scrape_method': 'playwright_authenticated'
                }
            )
            
            # Add to seen URLs
            self.seen_urls.add(post_url)
            
            return lead
            
        except Exception as e:
            print(f"    ⚠️  Error extracting post data: {e}")
            return None
    
    async def _scrape_keyword(self, keyword: str, posts_limit: int) -> list[Lead]:
        """
        Scrape LinkedIn posts for a single keyword with retry logic.
        
        Args:
            keyword: Search keyword
            posts_limit: Maximum posts to scrape for this keyword
            
        Returns:
            List of Lead objects
        """
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    print(f"  🔄 Retry attempt {attempt + 1}/{max_retries} for '{keyword}'")
                    await asyncio.sleep(random.uniform(10.0, 20.0))  # Wait before retry
                
                leads = await self._scrape_keyword_impl(keyword, posts_limit)
                
                # If we got results, return immediately
                if leads:
                    return leads
                
                # If no results and this was the last attempt, return empty
                if attempt == max_retries - 1:
                    print(f"  ⚠️  No leads found after {max_retries} attempts for '{keyword}'")
                    return []
                
            except PlaywrightTimeout:
                print(f"  ⚠️  Timeout on attempt {attempt + 1}/{max_retries}")
                if attempt == max_retries - 1:
                    return []
            except Exception as e:
                print(f"  ⚠️  Error on attempt {attempt + 1}/{max_retries}: {e}")
                if attempt == max_retries - 1:
                    return []
        
        return []
    
    async def _scrape_keyword_impl(self, keyword: str, posts_limit: int) -> list[Lead]:
        """
        Implementation of keyword scraping with infinite scroll pagination.
        
        Args:
            keyword: Search keyword
            posts_limit: Maximum posts to scrape for this keyword
            
        Returns:
            List of Lead objects
        """
        leads = []
        
        # Build search URL
        from urllib.parse import quote
        encoded_keyword = quote(keyword)
        search_url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_keyword}&sortBy=date_posted"
        
        print(f"  → Navigating to: {search_url[:80]}...")
        
        # Apply rate limiting
        await self._apply_rate_limit()
        
        # Navigate to search page
        await self.page.goto(search_url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(3)  # Wait for dynamic content
        
        # Check for authwall
        if 'authwall' in self.page.url or 'login' in self.page.url:
            print(f"  ⚠️  Authentication lost - redirected to login. Stopping.")
            return leads
        
        # Random mouse movement
        await self._random_mouse_movement()
        
        # Improved post selectors (prioritizing data attributes for stability)
        post_selectors = [
            'div[data-urn^="urn:li:activity:"]',
            'div[data-id^="urn:li:activity:"]',
            '.feed-shared-update-v2',
            '.feed-shared-update-v2__content',
            '[data-test-component="update-v2"]',
            '.update-v2-social-activity',
            'article'
        ]
        
        # Infinite scroll with stagnation detection
        previous_post_count = 0
        stagnation_count = 0
        max_stagnation = 3  # Stop after 3 consecutive scrolls with no new posts
        scroll_count = 0
        
        print(f"  🔄 Starting infinite scroll (target: {posts_limit} posts)...")
        
        while scroll_count < 50:  # Safety limit to prevent infinite loops
            # Get current post count
            current_post_elements = []
            for selector in post_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    if elements and len(elements) > current_post_elements:
                        current_post_elements = elements
                except Exception:
                    continue
            
            current_post_count = len(current_post_elements)
            
            # Check if we have enough posts
            if current_post_count >= posts_limit:
                print(f"  ✓ Reached target: {current_post_count} posts loaded")
                break
            
            # Check for stagnation (no new posts loaded)
            if current_post_count == previous_post_count:
                stagnation_count += 1
                if stagnation_count >= max_stagnation:
                    print(f"  ⚠️  No new posts after {max_stagnation} scrolls. Stopping at {current_post_count} posts.")
                    break
            else:
                stagnation_count = 0  # Reset stagnation counter
                print(f"  → Loaded {current_post_count} posts (target: {posts_limit})")
            
            previous_post_count = current_post_count
            
            # Scroll down
            await self._human_like_scroll()
            scroll_count += 1
            
            # Wait for content to load
            await asyncio.sleep(random.uniform(1.5, 3.0))
        
        # Find all post elements (final collection)
        post_elements = []
        for selector in post_selectors:
            try:
                elements = await self.page.query_selector_all(selector)
                if elements:
                    post_elements = elements
                    print(f"  ✓ Using selector: {selector} ({len(elements)} posts)")
                    break
            except Exception:
                continue
        
        if not post_elements:
            print(f"  ⚠️  No post elements found for '{keyword}'")
            return leads
        
        print(f"  → Found {len(post_elements)} post elements, extracting data...")
        
        # Extract data from each post
        for index, post_elem in enumerate(post_elements[:posts_limit]):
            try:
                lead = await self._extract_post_data(post_elem, keyword, index)
                if lead:
                    leads.append(lead)
                    
                    # Check if we've hit limit
                    if len(leads) >= posts_limit:
                        break
                        
            except Exception as e:
                print(f"    ⚠️  Error processing post {index}: {e}")
                continue
        
        print(f"  ✓ Extracted {len(leads)} leads from '{keyword}'")
        
        return leads
    
    async def scrape(self) -> list[Lead]:
        """
        Main scraping method - scrape all keywords.
        
        Returns:
            List of all leads scraped
        """
        all_leads = []
        
        try:
            # Setup browser
            await self._setup_browser()
            
            print(f"\n🔍 Starting LinkedIn Playwright scraping")
            print(f"   • Keywords: {len(self.keywords)}")
            print(f"   • Max posts per keyword: {self.max_posts_per_keyword}")
            print(f"   • Global lead limit: {self.max_total_leads}")
            print(f"   • Date filter: Past {self.days_filter} days" if self.days_filter > 0 else "   • Date filter: All time")
            
            # Scrape each keyword
            for idx, keyword in enumerate(self.keywords, 1):
                # Check global limit
                if len(all_leads) >= self.max_total_leads:
                    print(f"\n⚠️  Global lead limit reached ({self.max_total_leads} leads)")
                    print(f"   Stopping early (scraped {idx-1}/{len(self.keywords)} keywords)")
                    break
                
                print(f"\n  [{idx}/{len(self.keywords)}] Keyword: '{keyword}'")
                
                # Calculate remaining budget
                remaining_budget = self.max_total_leads - len(all_leads)
                posts_to_fetch = min(self.max_posts_per_keyword, remaining_budget)
                
                if posts_to_fetch <= 0:
                    break
                
                # Scrape keyword
                try:
                    leads = await self._scrape_keyword(keyword, posts_to_fetch)
                    if leads:
                        all_leads.extend(leads)
                        print(f"  → Total leads: {len(all_leads)}/{self.max_total_leads}")
                except Exception as e:
                    print(f"  ⚠️  Failed to scrape '{keyword}': {e}")
                    continue
                
                # Delay between keywords
                if idx < len(self.keywords):
                    delay = random.uniform(3.0, 6.0)
                    await asyncio.sleep(delay)
            
            print(f"\n✅ Scraping complete: {len(all_leads)} leads collected")
            print(f"   • Unique URLs: {len(self.seen_urls)}")
            print(f"   • Requests made: {self.request_count}")
            
        except Exception as e:
            print(f"\n❌ Scraping failed: {e}")
        finally:
            await self.cleanup()
        
        return all_leads
    
    async def cleanup(self) -> None:
        """Clean up browser resources."""
        try:
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            print("🧹 Browser cleaned up successfully")
        except Exception as e:
            print(f"⚠️  Error during cleanup: {e}")
    
    def __repr__(self) -> str:
        return (
            f"LinkedInPlaywrightScraper("
            f"keywords={len(self.keywords)}, "
            f"max_posts={self.max_posts_per_keyword}, "
            f"max_leads={self.max_total_leads}, "
            f"headless={self.headless})"
        )


# Async wrapper for use in main.py
async def scrape_with_playwright(
    linkedin_cookie: str,
    keywords: list[str],
    max_posts_per_keyword: int = 50,
    max_total_leads: int = 200,
    rate_limit: int = 10,
    headless: bool = True,
    days_filter: int = 30,
    proxy: str | None = None
) -> list[Lead]:
    """
    Convenience function for scraping with Playwright.
    
    Usage:
        leads = await scrape_with_playwright(
            linkedin_cookie=settings.linkedin_cookie,
            keywords=['tokenization', 'RWA'],
            max_posts_per_keyword=50,
            max_total_leads=200,
            proxy='http://proxy.example.com:8080'  # Optional
        )
    """
    scraper = LinkedInPlaywrightScraper(
        linkedin_cookie=linkedin_cookie,
        keywords=keywords,
        max_posts_per_keyword=max_posts_per_keyword,
        max_total_leads=max_total_leads,
        rate_limit=rate_limit,
        headless=headless,
        days_filter=days_filter,
        proxy=proxy
    )
    
    return await scraper.scrape()
