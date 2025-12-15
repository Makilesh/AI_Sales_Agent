

import asyncio
import random
import re
import time
import urllib.parse
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from models.lead import Lead
from scrapers.base import BaseScraper


class LinkedInPublicScraper(BaseScraper):
    """Production LinkedIn scraper for public content without authentication."""
    
    # Class-level request counter for daily limit
    _daily_request_count = 0
    _daily_reset_time = datetime.now()
    
    DAILY_LIMIT = 100
    MAX_RESULTS_PER_KEYWORD = 200
    RESULTS_PER_PAGE = 25  # LinkedIn shows ~25 results per page
    
    # Service categories for classification
    SERVICE_CATEGORIES = {
        'RWA': ['tokenization', 'real world asset', 'rwa', 'asset tokenization', 'security token', 'sto'],
        'DeFi': ['defi', 'decentralized finance', 'liquidity', 'yield farming', 'dex'],
        'NFT': ['nft', 'non-fungible token', 'digital art', 'collectible'],
        'Smart Contract': ['smart contract', 'solidity', 'ethereum contract', 'web3 development'],
        'Blockchain': ['blockchain', 'distributed ledger', 'consensus', 'cryptocurrency']
    }
    
    DEFAULT_USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ]
    
    def __init__(
        self,
        keywords: list[str],
        user_agents: list[str] | None = None,
        rate_limit: int = 2,  # requests per minute
        max_posts_per_keyword: int = 200,
        max_total_leads: int = 200,
        days_filter: int = 30,
        min_reactions: int = 0,
        strict_mode: bool = True  # Toggle between strict and loose inquiry filtering
    ) -> None:
        super().__init__(keywords, rate_limit, days_filter=days_filter)
        self.user_agents = user_agents or self.DEFAULT_USER_AGENTS
        self.session = requests.Session()
        self.max_posts_per_keyword = max_posts_per_keyword
        self.max_total_leads = max_total_leads
        self.days_filter = days_filter
        self.min_reactions = min_reactions
        self.strict_mode = strict_mode
        
    def _get_random_user_agent(self) -> str:
        """Select random user agent for request."""
        return random.choice(self.user_agents)
    
    def _build_search_headers(self, user_agent: str) -> dict:
        """Build headers for LinkedIn search request."""
        return {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
    
    def _is_blocked_response(self, response: requests.Response) -> bool:
        """Check if LinkedIn blocked the request."""
        return response.status_code in [403, 429, 999]
    
    async def _random_delay(self) -> None:
        """Apply random delay between 8-15 seconds."""
        delay = random.uniform(8.0, 15.0)
        await asyncio.sleep(delay)
    
    def _check_daily_limit(self) -> bool:
        """Check if daily request limit has been reached."""
        now = datetime.now()
        
        # Reset counter if new day
        if now.date() > self._daily_reset_time.date():
            LinkedInPublicScraper._daily_request_count = 0
            LinkedInPublicScraper._daily_reset_time = now
        
        return self._daily_request_count < self.DAILY_LIMIT
    
    def _increment_request_count(self) -> None:
        """Increment daily request counter."""
        LinkedInPublicScraper._daily_request_count += 1
    
    def _is_service_inquiry(self, text: str) -> bool:
        """
        Filter for genuine buyer inquiries asking for help/services.
        Supports strict mode (default) and loose mode via strict_mode flag.
        """
        if not text:
            return False
        
        text_lower = text.lower()
        
        # Primary inquiry phrases (strong signals)
        strong_inquiry_phrases = [
            "looking for", "need help", "need a", "need to hire", "seeking",
            "anyone know", "recommendations for", "suggestions for",
            "can anyone recommend", "who can help", "looking to hire",
            "need advice", "need assistance", "help with", "help me",
            "struggling with", "having trouble", "can't figure out",
            "budget for", "willing to pay", "price range", "cost estimate",
            "rfp for", "request for proposal", "quotes for", "quotation for",
            "vendor for", "service provider", "consultant needed",
            "contractor needed", "freelancer needed"
        ]
        
        # Weak inquiry signals (looser mode)
        weak_inquiry_phrases = [
            "interested in", "open to", "exploring", "any providers",
            "any recommendations", "does anyone", "has anyone tried",
            "what's the best", "which is better", "should i use"
        ]
        
        # Check for service category keywords
        has_category_keyword = any(
            keyword.lower() in text_lower 
            for categories in self.SERVICE_CATEGORIES.values() 
            for keyword in categories
        )
        
        # Strict mode: require strong inquiry phrase
        if self.strict_mode:
            has_inquiry = any(phrase in text_lower for phrase in strong_inquiry_phrases)
            if not has_inquiry:
                return False
        else:
            # Loose mode: strong OR (weak + category keyword)
            has_strong = any(phrase in text_lower for phrase in strong_inquiry_phrases)
            has_weak = any(phrase in text_lower for phrase in weak_inquiry_phrases)
            
            if not (has_strong or (has_weak and has_category_keyword)):
                return False
        
        # STRICT blockers - reject educational/news/promotional content
        content_blockers = [
            # Promotional/company announcements
            "proud to announce", "excited to share", "thrilled to announce",
            "we are pleased", "we're launching", "join us", "register now",
            "check out our", "our platform", "our solution", "we provide",
            "we offer", "our team", "our company", "partnership with",
            "signed a deal", "collaborated with", "working with",
            
            # Educational/thought leadership (these dominate LinkedIn)
            "imagine owning", "the future of", "is changing the way",
            "is reshaping", "is transforming", "is redefining",
            "will become", "is emerging as", "key trends",
            "deep dive into", "just published", "my article",
            "reflections from", "what's next for", "the next frontier",
            "a convergence", "aligns with", "roadmap", "framework",
            
            # News/announcements
            "acquired", "acquisition", "announced", "authorization",
            "last week", "yesterday", "just over", "has officially",
            "blackrock", "securitize", "kraken", "coinbase",
            
            # Job postings (hiring, not seeking service)
            "we are hiring", "we're hiring", "job opening",
            "position:", "location:", "duration:", "job description",
            "send resumes to", "apply now", "submit your resume",
            "candidates / vendors", "years experience", "yrs exp"
        ]
        
        if any(blocker in text_lower for blocker in content_blockers):
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
    
    def _simplify_keyword(self, keyword: str) -> str:
        """Simplify multi-word keywords for better LinkedIn search matching."""
        keyword_parts = keyword.split()
        if len(keyword_parts) > 2:
            # Use the most distinctive word (usually the last substantive word)
            simple_keyword = keyword_parts[-1] if keyword_parts[-1] not in ['developer', 'consultant', 'engineer', 'project', 'platform', 'solution', 'expert'] else keyword_parts[0]
            print(f"     ℹ️  Simplifying '{keyword}' → '{simple_keyword}' for LinkedIn search")
            return simple_keyword
        return keyword
    
    def _parse_relative_time(self, time_text: str) -> datetime:
        """
        Parse relative time text (e.g., '2 days ago', '1 week ago') into datetime.
        Returns approximate datetime based on current time.
        """
        if not time_text:
            return datetime.now()
        
        time_text_lower = time_text.lower().strip()
        now = datetime.now()
        
        # Extract number and unit
        # Patterns: "2 days ago", "1 week ago", "3 hours ago", "1 month ago"
        match = re.search(r'(\d+)\s*(second|minute|hour|day|week|month|year)s?\s*ago', time_text_lower)
        
        if not match:
            # Try without number (e.g., "a day ago", "an hour ago")
            if 'hour' in time_text_lower or 'hr' in time_text_lower:
                return now - timedelta(hours=1)
            elif 'day' in time_text_lower:
                return now - timedelta(days=1)
            elif 'week' in time_text_lower:
                return now - timedelta(weeks=1)
            elif 'month' in time_text_lower:
                return now - timedelta(days=30)
            return now
        
        amount = int(match.group(1))
        unit = match.group(2)
        
        if unit == 'second':
            return now - timedelta(seconds=amount)
        elif unit == 'minute':
            return now - timedelta(minutes=amount)
        elif unit == 'hour':
            return now - timedelta(hours=amount)
        elif unit == 'day':
            return now - timedelta(days=amount)
        elif unit == 'week':
            return now - timedelta(weeks=amount)
        elif unit == 'month':
            return now - timedelta(days=amount * 30)
        elif unit == 'year':
            return now - timedelta(days=amount * 365)
        
        return now
    
    def _extract_timestamp_from_post_id(self, url: str) -> datetime | None:
        """
        Extract timestamp from LinkedIn post ID (Snowflake-like ID).
        Post URLs often contain 'activity-{post_id}' or 'ugcPost:{post_id}'.
        The post_id is a 19-digit number where first 41 bits are timestamp.
        """
        try:
            # Extract post ID from URL patterns
            # Examples: 
            # - /feed/update/urn:li:activity:7123456789012345678/
            # - /posts/username_ugcPost:7123456789012345678
            match = re.search(r'(?:activity[:-]|ugcPost[:-])(\d{19})', url)
            
            if not match:
                return None
            
            post_id = int(match.group(1))
            
            # LinkedIn uses Snowflake-like IDs: 
            # First 41 bits = milliseconds since custom epoch
            # Right shift by 22 bits to get timestamp in milliseconds
            timestamp_ms = post_id >> 22
            
            # LinkedIn epoch appears to be around 2015-01-01 (Unix timestamp: 1420070400000 ms)
            # Adding this to the extracted timestamp
            linkedin_epoch_ms = 1420070400000
            actual_timestamp_ms = timestamp_ms + linkedin_epoch_ms
            
            # Convert to datetime
            timestamp = datetime.fromtimestamp(actual_timestamp_ms / 1000)
            
            return timestamp
        except Exception as e:
            print(f"    ⚠️  Failed to extract timestamp from post ID: {e}")
            return None
    
    async def scrape(self) -> list[Lead]:
        """Scrape public LinkedIn content for all keywords with service inquiry filtering."""
        if not self._check_daily_limit():
            print(f"⚠️  LinkedIn daily limit reached ({self.DAILY_LIMIT} requests). Skipping.")
            return []
        
        all_leads: list[Lead] = []
        seen_urls = set()  # Track URLs to avoid duplicates
        
        print(f"🔍 Starting LinkedIn public scraping")
        print(f"   • Max posts per keyword: {self.max_posts_per_keyword}")
        print(f"   • Global lead limit: {self.max_total_leads}")
        print(f"   • Keywords to search: {len(self.keywords)}")
        print(f"   • Date filter: Past {self.days_filter} days" if self.days_filter > 0 else "   • Date filter: All time")
        print(f"   • Filtering mode: {'STRICT' if self.strict_mode else 'LOOSE'}")
        print(f"🎯 Focus: SERVICE INQUIRIES ONLY")
        print("   Looking for: People explicitly asking for services (not promotional/educational content)")
        
        for idx, keyword in enumerate(self.keywords, 1):
            # Check global limit BEFORE scraping each keyword
            if len(all_leads) >= self.max_total_leads:
                print(f"\n⚠️  Global lead limit reached ({self.max_total_leads} leads)")
                print(f"   Stopping early (scraped {idx-1}/{len(self.keywords)} keywords)")
                print(f"   💰 Request savings: Skipped {len(self.keywords) - idx + 1} keywords")
                break
            
            if not self._check_daily_limit():
                print(f"\n⚠️  Daily request limit reached during scraping. Stopping.")
                break
            
            try:
                # Calculate remaining budget for this keyword
                remaining_budget = self.max_total_leads - len(all_leads)
                posts_to_fetch = min(self.max_posts_per_keyword, remaining_budget)
                
                if posts_to_fetch <= 0:
                    break
                
                print(f"\n  [{idx}/{len(self.keywords)}] Keyword: '{keyword}' (budget: {posts_to_fetch} posts)")
                leads = await self._search_keyword(keyword, posts_to_fetch)
                
                # Filter for service inquiries and add classification
                unique_leads = []
                for lead in leads:
                    if lead.url not in seen_urls:
                        # Check if it's actually a service inquiry
                        full_text = lead.content + " " + (lead.title or "")
                        is_inquiry = self._is_service_inquiry(full_text)
                        
                        if is_inquiry:
                            service_types = self._classify_service_type(full_text)
                            lead.metadata['service_types'] = service_types
                            lead.metadata['service_inquiry'] = True
                            
                            unique_leads.append(lead)
                            seen_urls.add(lead.url)
                
                if unique_leads:
                    all_leads.extend(unique_leads)
                    print(f"  ✓ Extracted {len(unique_leads)} service leads | Total: {len(all_leads)}/{self.max_total_leads}")
                else:
                    print(f"  ℹ No service inquiries found for '{keyword}'")
                
                # Random delay between keywords
                if idx < len(self.keywords) and self._check_daily_limit():
                    await self._random_delay()
                    
            except Exception as e:
                print(f"  ⚠️  Error searching LinkedIn for '{keyword}': {e}")
                continue
        
        print(f"\n✅ Scraping complete: {len(all_leads)} LinkedIn service leads collected")
        return all_leads
    
    async def _search_keyword(self, keyword: str, posts_limit: int = None) -> list[Lead]:
        """
        Search LinkedIn for a single keyword with pagination support.
        Fetches multiple pages until posts_limit is reached or no more results.
        """
        leads: list[Lead] = []
        
        # Use custom limit if provided (for rate limiting), otherwise use default
        effective_limit = posts_limit if posts_limit is not None else self.max_posts_per_keyword
        
        # Simplify keyword for better search matching
        search_keyword = self._simplify_keyword(keyword)
        encoded_keyword = urllib.parse.quote(search_keyword)
        
        # Build date filter parameter (f_TPR = time posted range in seconds)
        date_filter_param = ""
        if self.days_filter > 0:
            seconds = self.days_filter * 86400
            date_filter_param = f"&f_TPR=r{seconds}"
            print(f"     📅 Server-side date filter: past {self.days_filter} days ({seconds}s)")
        
        # Pagination loop
        page = 0
        total_cards_processed = 0
        filtered_by_date = 0
        filtered_by_engagement = 0
        
        while len(leads) < effective_limit:
            # Check if we've hit daily limit
            if not self._check_daily_limit():
                print(f"  ⚠️  Daily limit reached during pagination. Stopping.")
                break
            
            # Build search URL with pagination
            page_start = page * self.RESULTS_PER_PAGE
            search_url = (
                f"https://www.linkedin.com/search/results/content/"
                f"?keywords={encoded_keyword}"
                f"&origin=GLOBAL_SEARCH_HEADER"
                f"&start={page_start}"
                f"{date_filter_param}"
                f"&sortBy=date_posted"  # Sort by recency
            )
            
            # Apply rate limiting
            await self._apply_rate_limit()
            
            # Select random user agent and build headers
            user_agent = self._get_random_user_agent()
            headers = self._build_search_headers(user_agent)
            
            try:
                # Make request in thread to avoid blocking
                print(f"  → Page {page + 1}: {search_url[:100]}...")
                response = await asyncio.to_thread(
                    self.session.get,
                    search_url,
                    headers=headers,
                    timeout=15
                )
                
                self._increment_request_count()
                
                # Check if blocked
                if self._is_blocked_response(response):
                    print(f"  ⚠️  LinkedIn blocked request (status {response.status_code}). Stopping pagination.")
                    break
                
                if response.status_code != 200:
                    print(f"  ⚠️  Unexpected status code: {response.status_code}. Stopping pagination.")
                    break
                
                # Parse HTML
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find search result cards (flexible class matching for 2025 HTML structure)
                result_cards = soup.find_all(['div', 'li'], class_=lambda x: x and (
                    'entity-result' in x or 
                    'update-components-actor' in x or
                    'reusable-search__result' in x or
                    'search-result' in x or
                    'feed-shared-update-v2' in x or
                    'scaffold-finite-scroll__content' in x
                ))
                
                if not result_cards:
                    print(f"  ℹ️  No more results found on page {page + 1}. Stopping pagination.")
                    break
                
                print(f"  → Found {len(result_cards)} result cards on page {page + 1}")
                
                # Parse results from this page
                page_leads = 0
                for index, card in enumerate(result_cards):
                    # Check if we've reached the limit
                    if len(leads) >= effective_limit:
                        break
                    
                    try:
                        lead = self._parse_search_result(card, keyword, total_cards_processed + index)
                        if lead:
                            # Apply date filter (fallback to post-level filtering)
                            if self.days_filter > 0:
                                lead_age_days = (datetime.now() - lead.timestamp).days
                                if lead_age_days > self.days_filter:
                                    filtered_by_date += 1
                                    continue
                            
                            # Apply engagement filter
                            if lead.engagement_score < self.min_reactions:
                                filtered_by_engagement += 1
                                continue
                            
                            leads.append(lead)
                            page_leads += 1
                    except Exception as e:
                        print(f"  ⚠️  Error parsing result {index}: {e}")
                        continue
                
                total_cards_processed += len(result_cards)
                print(f"  → Scraped {page_leads} leads from page {page + 1} | Total: {len(leads)}/{effective_limit}")
                
                # If no leads found on this page, stop pagination
                if page_leads == 0:
                    print(f"  ℹ️  No qualifying leads on page {page + 1}. Stopping pagination.")
                    break
                
                # Move to next page
                page += 1
                
                # Add delay between page requests to avoid detection
                if len(leads) < effective_limit:
                    await self._random_delay()
                
            except requests.RequestException as e:
                print(f"  ⚠️  Request failed for page {page + 1}: {e}")
                break
            except Exception as e:
                print(f"  ⚠️  Unexpected error on page {page + 1}: {e}")
                break
        
        print(f"  → Completed {page} pages, scraped {len(leads)} raw posts from '{keyword}'")
        if filtered_by_date > 0:
            print(f"  🗓️  Filtered out {filtered_by_date} posts older than {self.days_filter} days")
        if filtered_by_engagement > 0:
            print(f"  📊 Filtered out {filtered_by_engagement} posts with < {self.min_reactions} reactions")
        
        return leads
    
    def _parse_search_result(self, card, keyword: str, index: int) -> Lead | None:
        """
        Parse a single search result card into a Lead with improved timestamp extraction.
        Handles 2025 LinkedIn HTML structure with flexible class matching.
        """
        try:
            # Extract author name (flexible class matching)
            author_elem = card.find(['span', 'div'], class_=lambda x: x and (
                'entity-result__title-text' in x or
                'update-components-actor__name' in x or
                'actor-name' in x or
                'feed-shared-actor__name' in x or
                'update-components-actor__name-text' in x
            ))
            author = author_elem.get_text(strip=True) if author_elem else "LinkedIn User"
            
            # Extract content/snippet (flexible class matching)
            content_elem = card.find(['p', 'div', 'span'], class_=lambda x: x and (
                'entity-result__summary' in x or
                'update-components-text' in x or
                'feed-shared-text' in x or
                'feed-shared-update-v2__description' in x or
                'break-words' in x
            ))
            content = content_elem.get_text(strip=True) if content_elem else ""
            
            # Extract title (flexible class matching)
            title_elem = card.find(['a', 'span'], class_=lambda x: x and (
                'app-aware-link' in x or
                'entity-result__title' in x or
                'update-components-actor__title' in x
            ))
            title = title_elem.get_text(strip=True) if title_elem else keyword
            
            # Combine title and content
            full_content = f"{title}\n\n{content}" if content else title
            full_content = full_content[:500]  # Limit to 500 chars
            
            # Extract URL
            link_elem = card.find('a', href=True)
            url = link_elem['href'] if link_elem else f"https://www.linkedin.com/search/results/content/?keywords={urllib.parse.quote(keyword)}"
            
            # Clean URL (remove tracking parameters)
            if '?' in url and not url.startswith('http'):
                url = f"https://www.linkedin.com{url.split('?')[0]}"
            elif not url.startswith('http'):
                url = f"https://www.linkedin.com{url}"
            
            # Extract timestamp (improved extraction with multiple fallbacks)
            timestamp = datetime.now()  # Default fallback
            timestamp_method = "default"
            
            # Method 1: Look for relative time text (most reliable in public HTML)
            time_elem = card.find(['span', 'time'], class_=lambda x: x and (
                'feed-shared-actor__sub-description' in x or
                'visually-hidden' in x or
                'update-components-actor__sub-description' in x or
                't-black--light' in x or
                'update-components-actor__supplementary-actor-info' in x
            ))
            
            if time_elem:
                time_text = time_elem.get_text(strip=True)
                parsed_time = self._parse_relative_time(time_text)
                if parsed_time != datetime.now():  # If parsing succeeded
                    timestamp = parsed_time
                    timestamp_method = f"relative_text: {time_text}"
            
            # Method 2: Try extracting from post ID in URL (Snowflake-like ID)
            if timestamp_method == "default":
                extracted_timestamp = self._extract_timestamp_from_post_id(url)
                if extracted_timestamp:
                    timestamp = extracted_timestamp
                    timestamp_method = "post_id_decode"
            
            # Method 3: Look for datetime attribute in time element
            if timestamp_method == "default":
                time_elem_with_datetime = card.find('time', attrs={'datetime': True})
                if time_elem_with_datetime:
                    try:
                        datetime_str = time_elem_with_datetime['datetime']
                        timestamp = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                        timestamp_method = "datetime_attribute"
                    except Exception:
                        pass
            
            # Extract engagement if visible (flexible class matching)
            engagement_elem = card.find(['span', 'button', 'div'], class_=lambda x: x and (
                'reaction' in x.lower() or 
                'social-details-social-counts' in x or
                'social-counts' in x
            ) if x else False)
            
            engagement_score = 0
            if engagement_elem:
                engagement_text = engagement_elem.get_text(strip=True)
                # Try to extract number
                numbers = re.findall(r'\d+', engagement_text)
                if numbers:
                    engagement_score = int(numbers[0])
            
            # Validate content
            if not full_content or len(full_content) < 10:
                return None
            
            return Lead(
                source='linkedin_public',
                author=author,
                content=full_content,
                timestamp=timestamp,
                url=url,
                title=title,
                engagement_score=engagement_score,
                metadata={
                    'search_query': keyword,
                    'result_position': index,
                    'is_public_search': True,
                    'scrape_method': 'public_no_auth',
                    'timestamp_method': timestamp_method  # Track how timestamp was extracted
                }
            )
            
        except Exception as e:
            print(f"    ⚠️  Parse error: {e}")
            return None
    
    def __repr__(self) -> str:
        return f"LinkedInPublicScraper(keywords={len(self.keywords)}, daily_requests={self._daily_request_count}/{self.DAILY_LIMIT})"
