

from dataclasses import dataclass, field
from decouple import config


@dataclass
class RedditConfig:
    """Reddit API configuration."""
    client_id: str = config("REDDIT_CLIENT_ID", default="")
    client_secret: str = config("REDDIT_CLIENT_SECRET", default="")
    user_agent: str = config("REDDIT_USER_AGENT", default="LeadScrapingBot/1.0")
    rate_limit: int = 60  # requests per minute (PRAW default)
    subreddits: list[str] = field(default_factory=lambda: [
        # TIER 1: EXPLICIT SERVICE-REQUEST SUBREDDITS (High conversion)
        "forhire",  # People posting job/service requests
        "slavelabour",  # Small gigs and tasks
        "Jobs4Bitcoins",  # Crypto-related work
        "hire",  # General hiring/service requests
        "freelance_forhire",  # Freelance service requests
        "hireawriter",  # Hiring requests (can include tech writers)
        "GetEmployed",  # Job/service seeking
        
        # TIER 2: BUSINESS HELP-SEEKING (Medium conversion)
        "entrepreneur",  # Business owners asking for help
        "startups",  # Startup founders seeking services
        "smallbusiness",  # Small business help requests
        "SaaS",  # SaaS business discussions
        "Entrepreneur_Ideas",  # Entrepreneurs exploring solutions
        
        # TIER 3: TECH-SPECIFIC WITH HELP REQUESTS (Medium-Low conversion)
        "learnmachinelearning",  # People asking for help
        "cryptocurrency",  # Crypto help/advice
        "CryptoTechnology",  # Technical crypto questions
        "web3",  # Web3 development help
        "ethdev",  # Ethereum development help
        "solidity",  # Smart contract help
        "cryptodevs",  # Crypto developers asking questions
        "realestateinvesting",  # Real estate investors (RWA target)
        "RealEstate",  # Real estate professionals (RWA target)
        
        # TIER 4: RWA-SPECIFIC SUBREDDITS (High relevance for Shamla Tech)
        "tokenization",  # Asset tokenization discussions
        "defi",  # DeFi and tokenized assets
        "investing",  # General investment discussions (RWA opportunities)
        "CommercialRealEstate",  # Commercial property tokenization
        "RealEstateInvestments",  # Property investment (tokenization fit)
        "SecurityTokens",  # Security token offerings
        "assetmanagement",  # Asset management (tokenization candidates)
    ])


@dataclass
class DiscordConfig:
    """Discord API configuration."""
    bot_token: str = config("DISCORD_BOT_TOKEN", default="")
    rate_limit: int = 50  # requests per second
    channels: list[str] = field(default_factory=lambda: [
        # Add your Discord channel IDs here
        # How to get: Right-click any channel → "Copy Channel ID"
        
        "1118264005207793674",  # Perplexity: #ask-community
        # Add more channel IDs here if needed:
        # "another_channel_id",  # Example: another channel
    ])  # Channel IDs to monitor
    guilds: list[str] = field(default_factory=list)  # Guild IDs to monitor (optional)


@dataclass
class SlackConfig:
    """Slack API configuration."""
    bot_token: str = config("SLACK_BOT_TOKEN", default="")
    app_token: str = config("SLACK_APP_TOKEN", default="")
    rate_limit: int = 1  # requests per second (Tier 1 = 1/sec, Tier 2+ = 100-20k/min)
    channels: list[str] = field(default_factory=list)  # Channel IDs to monitor
    workspaces: list[str] = field(default_factory=list)  # Workspace IDs


@dataclass
class LinkedInPublicConfig:
    """EXPERIMENTAL: LinkedIn public scraping (no login, high ban risk)."""
    enabled: bool = config("LINKEDIN_PUBLIC_ENABLED", default=False, cast=bool)
    rate_limit: int = 2  # requests per minute (NEVER increase)
    max_results_per_keyword: int = 10  # Single page only
    max_daily_requests: int = 20  # Hard daily limit
    delay_min_seconds: float = 8.0
    delay_max_seconds: float = 15.0


@dataclass
class LinkedInApifyConfig:
    """LinkedIn scraping via Apify API (production-ready, no account risk)."""
    enabled: bool = config("LINKEDIN_APIFY_ENABLED", default=False, cast=bool)
    apify_token: str = config("APIFY_TOKEN", default="")
    actor_id: str = config("LINKEDIN_APIFY_ACTOR", default="apify/linkedin-posts-scraper")
    max_posts_per_keyword: int = config("LINKEDIN_MAX_POSTS", default=200, cast=int)  # Increase for more results
    rate_limit: int = 10  # Apify API calls per minute
    days_filter: int = config("LINKEDIN_DAYS_FILTER", default=30, cast=int)  # Only posts from last N days
    
    # LinkedIn authentication (required by some actors)
    linkedin_cookie: str = config("LINKEDIN_COOKIE", default="")  # li_at cookie value
    proxy_config: str = config("LINKEDIN_PROXY", default="")  # Optional proxy URL
    
    # Content type configuration
    scrape_posts: bool = True  # Regular LinkedIn posts
    scrape_articles: bool = True  # LinkedIn articles
    scrape_discussions: bool = True  # Discussion threads
    scrape_comments: bool = True  # Post comments
    scrape_reactions: bool = True  # Like/reaction data
    min_reactions: int = config("LINKEDIN_MIN_REACTIONS", default=0, cast=int)  # Minimum engagement (0 = all posts)
    
    # Filtering options
    only_posts: bool = True  # Exclude company updates/ads
    include_sponsored: bool = False  # Include sponsored content
    min_reactions: int = 0  # Minimum reactions to consider


@dataclass
class ScrapingConfig:
    """General scraping parameters - SERVICE INQUIRY FOCUSED."""
    
    # ===================================================================
    # PLATFORM-SPECIFIC KEYWORD PRESETS
    # ===================================================================
    # Reddit vs LinkedIn have different content types and search behaviors
    # Use --service flag: python main.py --sources reddit --service rwa_reddit
    #                or: python main.py --sources linkedin_apify --service rwa_linkedin
    
    # REDDIT BEHAVIOR:
    # - Searches post titles AND content
    # - Casual/informal language
    # - Mix of questions, advice-seeking, hiring posts
    # - Best in r/forhire, r/slavelabour (explicit gig posts)
    
    # LINKEDIN BEHAVIOR:
    # - Searches post content (literal keyword matching)
    # - Professional language
    # - Mix of announcements, thought leadership, job posts
    # - Returns posts CONTAINING keywords (not necessarily requests)
    
    # ===================================================================
    # SHAMLA TECH COMPETITORS (India-based Web3/Blockchain firms)
    # ===================================================================
    # Direct competitors in RWA tokenization, DeFi, Web3 development
    COMPETITORS = [
        # Tier 1: Direct RWA & Web3 competitors
        "Antier Solutions", "Accubits Technologies", "Somish Blockchain Labs",
        "LeewayHertz", "Primafelicitas", "SoluLab", "IdeaUsher",
        "Tech Alchemy", "Codezeros",
        
        # Tier 2: General blockchain/Web3 dev companies
        "NetSet Software Solutions", "Nadcab Labs", "NADCAB",
        "Dev Technosys", "RedDuck", "Quytech",
        "Owebest Technologies", "TAKSH IT Solutions",
        
        # Common variations for matching
        "Antier", "Accubits", "Somish", "Leeway Hertz",
        "SoluLab", "Codezeros", "NetSet", "Nadcab"
    ]
    
    KEYWORD_PRESETS = {
        # OPTIMIZED: 8 core presets, 15 keywords each, no platform variants

        # ============================================================
        # 1. COMPETITOR FRUSTRATION (cross-platform)
        # ============================================================
        'competitor_frustration': [
            "alternative to Antier", "alternative to LeewayHertz",
            "alternative to Accubits", "alternative to SoluLab",
            "alternative tokenization", "disappointed with current",
            "need new consultant", "switch provider",
            "blockchain consultant issues", "RWA platform not working",
            "tokenization too expensive", "Web3 agency overcharging",
            "better RWA solution", "replacing current vendor",
            "blockchain vendor comparison"
        ],
        
        # ============================================================
        # 2. RWA TOKENIZATION (cross-platform) - BUYER-FOCUSED
        # ============================================================
        'rwa': [
            "tokenization consultant", "RWA developer",
            "asset tokenization", "real estate tokenization",
            "tokenization platform", "fractional ownership",
            "security token offering", "STO platform",
            "tokenize real estate", "tokenization project",
            "tokenization service", "blockchain tokenization",
            "looking for RWA", "need tokenization", "hiring tokenization"
        ],
        
        # ============================================================
        # 3. CRYPTO/WEB3 (cross-platform)
        # ============================================================
        'crypto': [
            "crypto developer", "web3 consultant",
            "DeFi platform", "crypto integration",
            "smart contract developer", "web3 engineer",
            "DeFi consultant", "smart contract audit",
            "crypto payment", "blockchain developer",
            "need crypto help", "hiring crypto",
            "web3 project", "DeFi development", "crypto consultant"
        ],

        # ============================================================
        # 4. AI/ML (cross-platform)
        # ============================================================
        'ai': [
            "AI consultant", "machine learning engineer",
            "AI automation", "chatbot development",
            "AI integration", "ML model",
            "AI developer", "chatbot developer",
            "ML engineer", "AI specialist",
            "need AI help", "hiring AI",
            "AI project", "machine learning consultant", "AI automation project"
        ],

        # ============================================================
        # 5. BLOCKCHAIN (cross-platform)
        # ============================================================
        'blockchain': [
            "blockchain consultant", "blockchain developer",
            "smart contract", "blockchain integration",
            "distributed ledger", "blockchain architect",
            "smart contract engineer", "blockchain project",
            "need blockchain help", "hiring blockchain",
            "blockchain solution", "smart contract audit",
            "blockchain platform", "blockchain engineer", "blockchain specialist"
        ],

        # ============================================================
        # 6. WEB3 GENERAL (cross-platform)
        # ============================================================
        'web3': [
            "web3 developer", "web3 consultant",
            "web3 platform", "web3 integration",
            "web3 project", "web3 engineer",
            "decentralized app", "dApp developer",
            "web3 architect", "web3 solution",
            "need web3 help", "hiring web3",
            "web3 specialist", "web3 service", "web3 development"
        ],

        # ============================================================
        # 7. DEFI (cross-platform)
        # ============================================================
        'defi': [
            "DeFi developer", "DeFi consultant",
            "DeFi platform", "DeFi protocol",
            "DeFi integration", "DeFi project",
            "DeFi engineer", "DeFi solution",
            "liquidity pool", "yield farming",
            "staking platform", "DEX development",
            "DeFi architecture", "need DeFi help", "hiring DeFi"
        ],

        # ============================================================
        # 8. SMART CONTRACTS (cross-platform)
        # ============================================================
        'smart_contracts': [
            "smart contract developer", "smart contract audit",
            "Solidity developer", "smart contract engineer",
            "contract security", "smart contract project",
            "Ethereum developer", "smart contract consultant",
            "contract development", "smart contract specialist",
            "need smart contract", "hiring solidity",
            "smart contract review", "contract audit", "smart contract integration"
        ],
    }
    
    # ===================================================================
    # KEYWORD USAGE GUIDE (OPTIMIZED)
    # ===================================================================
    #
    # OPTIMIZED: All presets are now cross-platform (no _reddit/_linkedin variants)
    #
    # Usage examples:
    # python main.py --sources reddit --service rwa --qualify
    # python main.py --sources linkedin_apify --service rwa --qualify
    # python main.py --sources reddit --service crypto --qualify
    # python main.py --sources linkedin_apify --service blockchain --qualify
    #
    # Available services:
    # - competitor_frustration: Find leads dissatisfied with competitors
    # - rwa: RWA tokenization and fractional ownership
    # - crypto: Crypto/Web3 development
    # - ai: AI/ML automation and chatbots
    # - blockchain: Blockchain and distributed ledger
    # - web3: Web3 and dApp development
    # - defi: DeFi protocols and platforms
    # - smart_contracts: Smart contract development and audits
    #
    # python main.py --sources reddit,linkedin_apify --service rwa --qualify --max-total-leads 100
    # - Uses universal keywords
    # - Good for A/B testing which platform performs better
    # 
    # ===================================================================
    
    # Default keywords (used if --service not specified)
    # Optimized for Shamla Tech's RWA specialization
    keywords: list[str] = field(default_factory=lambda: [
        # PRIMARY: RWA-specific terms
        "tokenization",
        "RWA",
        "real world asset",
        "asset tokenization",
        "fractional ownership",
        
        # SECONDARY: Help-seeking with RWA context
        "tokenize real estate",
        "tokenize assets",
        "need tokenization",
        "tokenization platform",
        
        # TERTIARY: General help-seeking (fallback)
        "looking for blockchain consultant",
        "need blockchain developer",
    ])
    
    max_results_per_source: int = 100
    max_total_leads: int = 500  # OPTIMIZED: Global limit (increased from 200)
    days_filter: int = config("DAYS_FILTER", default=14, cast=int)  # OPTIMIZED: Universal date filter (increased from 7 days)
    scrape_interval_seconds: int = 300  # 5 minutes
    enable_sentiment_filter: bool = True
    min_engagement_score: int = 0  # minimum upvotes/reactions (0 = allow posts with no engagement)


@dataclass
class AppSettings:
    """Main application settings."""
    reddit: RedditConfig = field(default_factory=RedditConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
    linkedin_public: LinkedInPublicConfig = field(default_factory=LinkedInPublicConfig)
    linkedin_apify: LinkedInApifyConfig = field(default_factory=LinkedInApifyConfig)
    scraping: ScrapingConfig = field(default_factory=ScrapingConfig)
    
    # LinkedIn Playwright Settings
    linkedin_cookie: str = config("LINKEDIN_COOKIE", default="")
    linkedin_proxy: str = config("LINKEDIN_PROXY", default="")
    
    # LLM Qualification Settings
    openai_api_key: str = config("OPENAI_API_KEY", default="")
    llm_model: str = "gpt-4-turbo"
    min_confidence_score: float = 0.7
    max_concurrent_llm_requests: int = 5
    
    debug_mode: bool = config("DEBUG", default=False, cast=bool)
    log_level: str = config("LOG_LEVEL", default="INFO")

    def validate(self) -> bool:
        """Validate that required credentials are present."""
        valid = True
        if not self.reddit.client_id or not self.reddit.client_secret:
            print("Warning: Reddit credentials not configured")
            valid = False
        if not self.discord.bot_token:
            print("Warning: Discord bot token not configured")
            valid = False
        if not self.slack.bot_token or not self.slack.app_token:
            print("Warning: Slack credentials not configured")
            valid = False
        if self.linkedin_public.enabled:
            print("⚠️  LinkedIn Public: EXPERIMENTAL - High ban risk. Consider Apify for production.")
        if self.linkedin_apify.enabled and not self.linkedin_apify.apify_token:
            print("Warning: LinkedIn Apify enabled but token not configured")
        return valid


# Global settings instance
settings = AppSettings()
