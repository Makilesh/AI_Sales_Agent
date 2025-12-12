

import asyncio
import random
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
        min_reactions: int = 0
    ) -> None:
        super().__init__(keywords, rate_limit, days_filter=days_filter)
        self.user_agents = user_agents or self.DEFAULT_USER_AGENTS
        self.session = requests.Session()
        self.max_posts_per_keyword = max_posts_per_keyword
        self.max_total_leads = max_total_leads
        self.days_filter = days_filter
        self.min_reactions = min_reactions
        
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
        STRICT filter: Only pass genuine buyer inquiries asking for help/services.
        Block: news, education, promotion, job posts, thought leadership, announcements.
        """
        if not text:
            return False
        
        text_lower = text.lower()
        
        # STRICT: Must have explicit help-seeking/buying phrases
        inquiry_phrases = [
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
        
        has_inquiry = any(phrase in text_lower for phrase in inquiry_phrases)
        if not has_inquiry:
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
        """Search LinkedIn for a single keyword."""
        leads: list[Lead] = []
        
        # Use custom limit if provided (for rate limiting), otherwise use default
        effective_limit = posts_limit if posts_limit is not None else self.max_posts_per_keyword
        
        # Simplify keyword for better search matching
        search_keyword = self._simplify_keyword(keyword)
        
        # Build search URL
        encoded_keyword = urllib.parse.quote(search_keyword)
        search_url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_keyword}&origin=GLOBAL_SEARCH_HEADER&start=0"
        
        # Apply rate limiting
        await self._apply_rate_limit()
        
        # Select random user agent and build headers
        user_agent = self._get_random_user_agent()
        headers = self._build_search_headers(user_agent)
        
        try:
            # Make request in thread to avoid blocking
            print(f"  → Fetching: {search_url[:80]}...")
            response = await asyncio.to_thread(
                self.session.get,
                search_url,
                headers=headers,
                timeout=15
            )
            
            self._increment_request_count()
            
            # Check if blocked
            if self._is_blocked_response(response):
                print(f"  ⚠️  LinkedIn blocked request (status {response.status_code}). Skipping.")
                return []
            
            if response.status_code != 200:
                print(f"  ⚠️  Unexpected status code: {response.status_code}")
                return []
            
            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find search result cards
            result_cards = soup.find_all(['div', 'li'], class_=lambda x: x and (
                'entity-result' in x or 
                'update-components-actor' in x or
                'reusable-search__result' in x or
                'search-result' in x
            ))
            
            print(f"  → Found {len(result_cards)} result cards")
            
            # Parse results (up to effective_limit)
            filtered_by_date = 0
            filtered_by_engagement = 0
            
            for index, card in enumerate(result_cards[:effective_limit]):
                try:
                    lead = self._parse_search_result(card, keyword, index)
                    if lead:
                        # Apply date filter
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
                except Exception as e:
                    print(f"  ⚠️  Error parsing result {index}: {e}")
                    continue
            
            print(f"  → Scraped {len(leads)} raw posts from '{keyword}'")
            if filtered_by_date > 0:
                print(f"  🗓️  Filtered out {filtered_by_date} posts older than {self.days_filter} days")
            if filtered_by_engagement > 0:
                print(f"  📊 Filtered out {filtered_by_engagement} posts with < {self.min_reactions} reactions")
            
        except requests.RequestException as e:
            print(f"  ⚠️  Request failed for '{keyword}': {e}")
        except Exception as e:
            print(f"  ⚠️  Unexpected error for '{keyword}': {e}")
        
        return leads
    
    def _parse_search_result(self, card, keyword: str, index: int) -> Lead | None:
        """Parse a single search result card into a Lead."""
        try:
            # Extract author name
            author_elem = card.find(['span', 'div'], class_=lambda x: x and (
                'entity-result__title-text' in x or
                'update-components-actor__name' in x or
                'actor-name' in x
            ))
            author = author_elem.get_text(strip=True) if author_elem else "LinkedIn User"
            
            # Extract content/snippet
            content_elem = card.find(['p', 'div'], class_=lambda x: x and (
                'entity-result__summary' in x or
                'update-components-text' in x or
                'feed-shared-text' in x
            ))
            content = content_elem.get_text(strip=True) if content_elem else ""
            
            # Extract title
            title_elem = card.find(['a', 'span'], class_=lambda x: x and (
                'app-aware-link' in x or
                'entity-result__title' in x
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
            
            # Extract engagement if visible
            engagement_elem = card.find(['span', 'button'], class_=lambda x: x and 'reaction' in x.lower() if x else False)
            engagement_score = 0
            if engagement_elem:
                engagement_text = engagement_elem.get_text(strip=True)
                # Try to extract number
                import re
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
                timestamp=datetime.now(),  # No reliable timestamp in search results
                url=url,
                title=title,
                engagement_score=engagement_score,
                metadata={
                    'search_query': keyword,
                    'result_position': index,
                    'is_public_search': True,
                    'scrape_method': 'public_no_auth'
                }
            )
            
        except Exception as e:
            print(f"    ⚠️  Parse error: {e}")
            return None
    
    def __repr__(self) -> str:
        return f"LinkedInPublicScraper(keywords={len(self.keywords)}, daily_requests={self._daily_request_count}/{self.DAILY_LIMIT})"
