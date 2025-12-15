"""
LinkedIn Selenium Scraper
Production-ready LinkedIn scraper using Selenium WebDriver with comprehensive anti-detection.
"""

import time
import random
import re
from datetime import datetime, timedelta
from typing import Optional
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from models.lead import Lead
from scrapers.base import BaseScraper


class LinkedInSeleniumScraper(BaseScraper):
    """
    LinkedIn scraper using Selenium WebDriver with anti-detection measures.
    
    Features:
    - Cookie-based authentication (li_at)
    - Search box simulation (human-like typing)
    - Infinite scroll with stagnation detection
    - Service type classification (RWA, Crypto, DeFi, etc.)
    - Date filtering (30 days default)
    - Proxy support
    - Random delays and mouse movements
    - Undetected ChromeDriver options
    """
    
    # Service categories for classification
    SERVICE_CATEGORIES = {
        'RWA': ['rwa', 'real world asset', 'tokenization', 'asset tokenization', 'security token'],
        'Crypto': ['crypto', 'cryptocurrency', 'bitcoin', 'ethereum', 'defi', 'web3'],
        'DeFi': ['defi', 'decentralized finance', 'yield', 'liquidity', 'amm'],
        'NFT': ['nft', 'non-fungible', 'collectible', 'digital art'],
        'Smart Contract': ['smart contract', 'solidity', 'vyper', 'contract audit'],
        'Blockchain': ['blockchain', 'distributed ledger', 'consensus', 'node'],
        'AI/ML': ['ai', 'artificial intelligence', 'machine learning', 'ml model', 'neural network']
    }
    
    # User agents for rotation
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    ]
    
    def __init__(
        self,
        linkedin_cookie: str,
        keywords: list[str],
        max_posts_per_keyword: int = 200,
        max_total_leads: int = 1000,
        rate_limit: int = 10,
        headless: bool = True,
        days_filter: int = 30,
        proxy: Optional[str] = None
    ):
        """
        Initialize LinkedIn Selenium scraper.
        
        Args:
            linkedin_cookie: LinkedIn li_at cookie value
            keywords: List of search keywords
            max_posts_per_keyword: Max posts per keyword (budget)
            max_total_leads: Global limit across all keywords
            rate_limit: Requests per minute
            headless: Run browser in headless mode
            days_filter: Only scrape posts from last N days
            proxy: Optional proxy (format: http://user:pass@host:port)
        """
        super().__init__(keywords, max_total_leads)
        self.linkedin_cookie = linkedin_cookie
        self.max_posts_per_keyword = max_posts_per_keyword
        self.max_total_leads = max_total_leads
        self.headless = headless
        self.days_filter = days_filter
        self.proxy = proxy
        self.rate_limit = rate_limit
        
        # WebDriver objects (initialized in _setup_driver)
        self.driver: Optional[webdriver.Chrome] = None
        self.wait: Optional[WebDriverWait] = None
        
        # Tracking
        self.seen_urls = set()
        self.request_count = 0
        self.last_request_time = time.time()
    
    def _setup_driver(self):
        """Initialize Selenium WebDriver with anti-detection measures."""
        print("🚀 Initializing Selenium WebDriver...")
        
        # Select random user agent
        user_agent = random.choice(self.USER_AGENTS)
        
        # Chrome options with anti-detection
        chrome_options = Options()
        
        # Headless mode
        if self.headless:
            chrome_options.add_argument('--headless=new')
        
        # Anti-detection arguments
        chrome_options.add_argument(f'user-agent={user_agent}')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-setuid-sandbox')
        chrome_options.add_argument('--disable-infobars')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--start-maximized')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--disable-popup-blocking')
        
        # Additional stealth options
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Proxy support
        if self.proxy:
            chrome_options.add_argument(f'--proxy-server={self.proxy}')
            print(f"   • Proxy: {self.proxy.split('@')[-1] if '@' in self.proxy else self.proxy}")
        
        # Preferences
        prefs = {
            "profile.default_content_setting_values.notifications": 2,
            "profile.default_content_settings.popups": 0,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        print(f"   • User Agent: {user_agent[:50]}...")
        print(f"   • Headless: {self.headless}")
        
        try:
            # Initialize driver
            self.driver = webdriver.Chrome(options=chrome_options)
            self.wait = WebDriverWait(self.driver, 10)
            
            # Execute CDP commands to hide webdriver property
            self.driver.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": user_agent
            })
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            # Add cookie and verify authentication
            print("🔐 Verifying authentication...")
            self.driver.get('https://www.linkedin.com')
            time.sleep(2)
            
            # Add li_at cookie
            self.driver.add_cookie({
                'name': 'li_at',
                'value': self.linkedin_cookie,
                'domain': '.linkedin.com',
                'path': '/',
                'secure': True,
                'httpOnly': True
            })
            
            # Navigate to feed to verify login
            self.driver.get('https://www.linkedin.com/feed/')
            time.sleep(3)
            
            # Check if logged in
            current_url = self.driver.current_url
            if 'authwall' in current_url or 'login' in current_url or 'checkpoint' in current_url:
                print(f"  ⚠️  Authentication failed - redirected to: {current_url}")
                raise Exception(f"Authentication failed. Your li_at cookie may be expired. Current URL: {current_url}")
            
            print("✅ Driver initialized and authenticated successfully")
            
        except Exception as e:
            print(f"❌ Failed to initialize driver: {e}")
            if self.driver:
                self.driver.quit()
            raise
    
    def _apply_rate_limit(self):
        """Apply rate limiting with human-like delays."""
        self.request_count += 1
        
        # Calculate delay
        elapsed = time.time() - self.last_request_time
        min_delay = 60.0 / self.rate_limit  # Minimum delay between requests
        
        if elapsed < min_delay:
            sleep_time = min_delay - elapsed + random.uniform(2, 5)  # Add human delay
            time.sleep(sleep_time)
        else:
            time.sleep(random.uniform(2, 5))  # Always add some delay
        
        self.last_request_time = time.time()
    
    def _human_like_scroll(self):
        """Simulate human-like scrolling behavior."""
        # Random scroll distance
        scroll_amount = random.randint(300, 800)
        self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
        time.sleep(random.uniform(1, 2.5))
    
    def _parse_relative_time(self, time_text: str) -> Optional[datetime]:
        """
        Parse relative time strings like '2h ago', '3d ago', '1w ago'.
        
        Args:
            time_text: Time string from LinkedIn post
            
        Returns:
            datetime object or None if unparseable
        """
        if not time_text:
            return None
        
        time_text = time_text.lower().strip()
        now = datetime.now()
        
        # Pattern: number + unit
        match = re.search(r'(\d+)\s*(h|hr|hour|d|day|w|wk|week|mo|month|y|yr|year)', time_text)
        if not match:
            return None
        
        amount = int(match.group(1))
        unit = match.group(2)
        
        if unit in ['h', 'hr', 'hour']:
            return now - timedelta(hours=amount)
        elif unit in ['d', 'day']:
            return now - timedelta(days=amount)
        elif unit in ['w', 'wk', 'week']:
            return now - timedelta(weeks=amount)
        elif unit in ['mo', 'month']:
            return now - timedelta(days=amount * 30)
        elif unit in ['y', 'yr', 'year']:
            return now - timedelta(days=amount * 365)
        
        return None
    
    def _classify_service_type(self, text: str) -> str:
        """
        Classify service type based on content.
        
        Args:
            text: Post content to analyze
            
        Returns:
            Service category string
        """
        if not text:
            return "Unknown"
        
        text_lower = text.lower()
        
        for category, keywords in self.SERVICE_CATEGORIES.items():
            if any(kw in text_lower for kw in keywords):
                return category
        
        return "General"
    
    def _extract_post_data(self, post_element) -> Optional[Lead]:
        """
        Extract lead data from a post element.
        
        Args:
            post_element: Selenium WebElement for post
            
        Returns:
            Lead object or None
        """
        try:
            # Extract author name
            author = "Unknown"
            author_selectors = [
                '.update-components-actor__name',
                '.feed-shared-actor__name',
                'span.update-components-actor__title',
                'span[dir="ltr"]'
            ]
            for selector in author_selectors:
                try:
                    author_elem = post_element.find_element(By.CSS_SELECTOR, selector)
                    author = author_elem.text.strip()
                    if author:
                        break
                except:
                    continue
            
            # Extract post content
            content = ""
            content_selectors = [
                '.feed-shared-update-v2__description',
                '.update-components-text',
                'div.feed-shared-text',
                'span.break-words'
            ]
            for selector in content_selectors:
                try:
                    # Try to click "see more" if available
                    try:
                        see_more = post_element.find_element(By.CSS_SELECTOR, '.feed-shared-inline-show-more-text__see-more-less-toggle')
                        see_more.click()
                        time.sleep(0.5)
                    except:
                        pass
                    
                    content_elem = post_element.find_element(By.CSS_SELECTOR, selector)
                    content = content_elem.text.strip()
                    if content:
                        break
                except:
                    continue
            
            # Extract post URL
            post_url = ""
            try:
                # Try to find link to post
                link_selectors = [
                    'a[href*="/feed/update/"]',
                    'a[data-control-name="feed_post"]',
                    'a.app-aware-link'
                ]
                for selector in link_selectors:
                    try:
                        link_elem = post_element.find_element(By.CSS_SELECTOR, selector)
                        post_url = link_elem.get_attribute('href')
                        if post_url and 'feed/update' in post_url:
                            break
                    except:
                        continue
            except:
                pass
            
            # Check if duplicate
            if post_url and post_url in self.seen_urls:
                return None
            
            # Extract timestamp
            timestamp_text = ""
            try:
                time_elem = post_element.find_element(By.CSS_SELECTOR, 'time, .update-components-actor__sub-description')
                timestamp_text = time_elem.text.strip()
            except:
                pass
            
            # Parse and filter by date
            post_date = self._parse_relative_time(timestamp_text)
            if post_date:
                cutoff_date = datetime.now() - timedelta(days=self.days_filter)
                if post_date < cutoff_date:
                    return None  # Too old
            
            # Must have content
            if not content or len(content) < 20:
                return None
            
            # Classify service type
            service_type = self._classify_service_type(content)
            
            # Mark as seen
            if post_url:
                self.seen_urls.add(post_url)
            
            # Create lead
            lead = Lead(
                name=author,
                platform="LinkedIn",
                url=post_url or self.driver.current_url,
                content=content,
                source="linkedin_selenium",
                service_type=service_type,
                scraped_at=datetime.now().isoformat()
            )
            
            return lead
            
        except Exception as e:
            # Silently skip problematic posts
            return None
    
    def _scrape_keyword(self, keyword: str, posts_limit: int) -> list[Lead]:
        """
        Scrape posts for a keyword with retry logic.
        
        Args:
            keyword: Search keyword
            posts_limit: Maximum posts to scrape
            
        Returns:
            List of Lead objects
        """
        max_retries = 3
        
        for attempt in range(max_retries):
            if attempt > 0:
                print(f"  🔄 Retry attempt {attempt + 1}/{max_retries} for '{keyword}'")
                time.sleep(random.uniform(10, 20))
            
            try:
                leads = self._scrape_keyword_impl(keyword, posts_limit)
                if leads or attempt == max_retries - 1:
                    return leads
            except Exception as e:
                print(f"  ⚠️  Error on attempt {attempt + 1}/{max_retries}: {str(e)[:100]}")
                if attempt == max_retries - 1:
                    return []
        
        return []
    
    def _scrape_keyword_impl(self, keyword: str, posts_limit: int) -> list[Lead]:
        """
        Implementation of keyword scraping using search box simulation.
        
        Args:
            keyword: Search keyword
            posts_limit: Maximum posts to scrape
            
        Returns:
            List of Lead objects
        """
        leads = []
        
        print(f"  → Searching for: '{keyword}' (using search box)")
        
        # Apply rate limiting
        self._apply_rate_limit()
        
        try:
            # Make sure we're on feed/home page
            current_url = self.driver.current_url
            if 'feed' not in current_url and 'linkedin.com' in current_url:
                print(f"  → Navigating to feed first...")
                self.driver.get('https://www.linkedin.com/feed/')
                time.sleep(3)
            
            # Find search box
            print(f"  → Finding search box...")
            search_input = None
            search_selectors = [
                'input[placeholder*="Search"]',
                '.search-global-typeahead__input',
                'input[aria-label*="Search"]',
                'input.search-global-typeahead__input'
            ]
            
            for selector in search_selectors:
                try:
                    search_input = self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if search_input:
                        break
                except:
                    continue
            
            if not search_input:
                raise Exception("Could not find search box")
            
            # Click search box
            search_input.click()
            time.sleep(random.uniform(0.5, 1))
            
            # Clear any existing text
            search_input.clear()
            time.sleep(random.uniform(0.3, 0.6))
            
            # Type keyword character by character (human-like)
            print(f"  → Typing keyword...")
            for char in keyword:
                search_input.send_keys(char)
                time.sleep(random.uniform(0.05, 0.15))
            
            time.sleep(random.uniform(1, 2))
            
            # Press Enter
            search_input.send_keys(Keys.RETURN)
            time.sleep(random.uniform(3, 5))
            
            # Wait for results page
            self.wait.until(EC.url_contains('search/results'))
            time.sleep(2)
            
            # Click on "Posts" filter
            print(f"  → Applying Posts filter...")
            try:
                posts_button = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Posts')]"))
                )
                posts_button.click()
                time.sleep(random.uniform(2, 4))
            except:
                print(f"  ℹ️  Posts filter not found, using current results...")
            
            # Start infinite scroll
            print(f"  🔄 Starting infinite scroll (target: {posts_limit} posts)...")
            scroll_count = 0
            max_scrolls = 50
            stagnation_count = 0
            previous_post_count = 0
            
            # Post selectors (try multiple)
            post_selectors = [
                'div[data-id^="urn:li:activity:"]',
                'div.feed-shared-update-v2',
                'div[data-urn^="urn:li:activity:"]',
                'div.update-v2-social-activity'
            ]
            
            while scroll_count < max_scrolls:
                # Find all post elements
                all_posts = []
                for selector in post_selectors:
                    try:
                        posts = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if posts:
                            all_posts = posts
                            break
                    except:
                        continue
                
                current_post_count = len(all_posts)
                
                # Check if we have enough
                if current_post_count >= posts_limit:
                    print(f"  ✓ Reached target: {current_post_count} posts loaded")
                    break
                
                # Check for stagnation (no new posts)
                if current_post_count == previous_post_count:
                    stagnation_count += 1
                    if stagnation_count >= 3:
                        print(f"  ⚠️  No new posts after {stagnation_count} scrolls. Stopping at {current_post_count} posts.")
                        break
                else:
                    stagnation_count = 0
                    print(f"  → Loaded {current_post_count} posts (target: {posts_limit})")
                
                previous_post_count = current_post_count
                
                # Scroll down
                self._human_like_scroll()
                scroll_count += 1
                
                # Occasional longer pause
                if scroll_count % 5 == 0:
                    time.sleep(random.uniform(2, 4))
            
            # Extract data from loaded posts
            all_posts = []
            for selector in post_selectors:
                try:
                    posts = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if posts:
                        all_posts = posts
                        print(f"  ✓ Using selector: {selector} ({len(posts)} posts)")
                        break
                except:
                    continue
            
            if not all_posts:
                print(f"  ⚠️  No post elements found for '{keyword}'")
                return leads
            
            print(f"  → Found {len(all_posts)} post elements, extracting data...")
            
            # Extract data from each post
            for idx, post in enumerate(all_posts[:posts_limit]):
                if len(leads) >= posts_limit:
                    break
                
                try:
                    lead = self._extract_post_data(post)
                    if lead:
                        leads.append(lead)
                except Exception as e:
                    # Skip problematic posts
                    continue
            
            print(f"  ✓ Extracted {len(leads)} leads from '{keyword}'")
            return leads
            
        except Exception as e:
            print(f"  ⚠️ Search box simulation failed: {str(e)[:100]}")
            return leads
    
    def scrape(self) -> list[Lead]:
        """
        Main scraping method - loops through keywords and collects leads.
        
        Returns:
            List of Lead objects
        """
        all_leads = []
        
        try:
            # Setup driver
            self._setup_driver()
            
            print(f"\n🔍 Starting LinkedIn Selenium scraping")
            print(f"   • Keywords: {len(self.keywords)}")
            print(f"   • Max posts per keyword: {self.max_posts_per_keyword}")
            print(f"   • Global lead limit: {self.max_total_leads}")
            print(f"   • Date filter: Past {self.days_filter} days\n")
            
            # Budget per keyword
            remaining_budget = self.max_total_leads
            
            for idx, keyword in enumerate(self.keywords, 1):
                if remaining_budget <= 0:
                    print(f"\n✓ Reached global limit of {self.max_total_leads} leads")
                    break
                
                print(f"\n  [{idx}/{len(self.keywords)}] Keyword: '{keyword}'")
                
                # Calculate budget for this keyword
                keywords_left = len(self.keywords) - idx + 1
                per_keyword_budget = min(
                    self.max_posts_per_keyword,
                    remaining_budget // keywords_left if keywords_left > 0 else remaining_budget
                )
                
                # Scrape keyword
                keyword_leads = self._scrape_keyword(keyword, per_keyword_budget)
                
                if keyword_leads:
                    all_leads.extend(keyword_leads)
                    remaining_budget -= len(keyword_leads)
                    print(f"  → Total leads: {len(all_leads)}/{self.max_total_leads}")
                else:
                    print(f"  ⚠️  No leads found for '{keyword}'")
            
            print(f"\n✅ Scraping complete: {len(all_leads)} leads collected")
            print(f"   • Unique URLs: {len(self.seen_urls)}")
            print(f"   • Requests made: {self.request_count}")
            
            return all_leads
            
        except KeyboardInterrupt:
            print("\n\n⚠️  Scraping interrupted by user")
            return all_leads
            
        except Exception as e:
            print(f"\n❌ Fatal error during scraping: {e}")
            return all_leads
            
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up driver resources."""
        if self.driver:
            try:
                self.driver.quit()
                print("\n🧹 Browser closed")
            except Exception as e:
                print(f"\n⚠️  Error during cleanup: {e}")


# Convenience function
def scrape_with_selenium(
    linkedin_cookie: str,
    keywords: list[str],
    max_posts_per_keyword: int = 200,
    max_total_leads: int = 1000,
    rate_limit: int = 10,
    headless: bool = True,
    days_filter: int = 30,
    proxy: Optional[str] = None
) -> list[Lead]:
    """
    Convenience function to scrape LinkedIn with Selenium.
    
    Args:
        linkedin_cookie: LinkedIn li_at cookie
        keywords: Search keywords
        max_posts_per_keyword: Max posts per keyword
        max_total_leads: Global lead limit
        rate_limit: Requests per minute
        headless: Run browser headless
        days_filter: Date filter in days
        proxy: Optional proxy string
        
    Returns:
        List of Lead objects
    """
    scraper = LinkedInSeleniumScraper(
        linkedin_cookie=linkedin_cookie,
        keywords=keywords,
        max_posts_per_keyword=max_posts_per_keyword,
        max_total_leads=max_total_leads,
        rate_limit=rate_limit,
        headless=headless,
        days_filter=days_filter,
        proxy=proxy
    )
    
    return scraper.scrape()
