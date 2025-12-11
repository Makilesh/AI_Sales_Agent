

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
    max_posts_per_keyword: int = 50
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
        # ============================================================
        # COMPETITOR FRUSTRATION - Find leads dissatisfied with competitors
        # ============================================================
        'competitor_frustration_reddit': [
            # Direct competitor complaints
            "Antier Solutions problems", "issues with Antier", "Antier delay",
            "Accubits problems", "Accubits expensive", "issues with Accubits",
            "LeewayHertz overpriced", "LeewayHertz delay", "LeewayHertz issues",
            "SoluLab problems", "SoluLab slow", "issues with SoluLab",
            "Primafelicitas expensive", "Primafelicitas delay",
            "Somish problems", "IdeaUsher issues", "Codezeros slow",
            
            # Alternative seeking (Reddit style)
            "alternative to Antier", "better than Antier Solutions",
            "alternative to LeewayHertz", "better than LeewayHertz",
            "alternative to Accubits", "cheaper than Accubits",
            "alternative to SoluLab", "better RWA platform than",
            "alternative to Primafelicitas", "alternative tokenization platform",
            
            # Generic frustration with current provider
            "current Web3 agency problems", "blockchain consultant issues",
            "RWA platform not working", "tokenization service delay",
            "Web3 developer unresponsive", "blockchain project stuck",
            "need new RWA consultant", "switch tokenization provider",
            "looking to change Web3 agency", "disappointed with current",
            
            # Budget/quality complaints
            "RWA tokenization too expensive", "Web3 agency overcharging",
            "blockchain consultant overpriced", "tokenization costs too high",
            "cheaper RWA solution", "affordable tokenization platform",
            "better value blockchain", "cost-effective Web3",
        ],
        
        'competitor_frustration_linkedin': [
            # Professional LinkedIn language
            "seeking alternative to [competitor]",
            "replacing current Web3 vendor",
            "RFP tokenization services",
            "evaluating RWA platforms",
            "blockchain vendor comparison",
            "Web3 agency RFP",
            "tokenization platform evaluation",
            "dissatisfied with current provider",
            "seeking better RWA solution",
            "competitive RWA pricing",
            "alternative blockchain consultant",
            "Web3 vendor alternatives",
        ],
        
        # ============================================================
        # REDDIT-OPTIMIZED: Short, casual, forum-style
        # ============================================================
        'rwa_reddit': [
            # Tier 1: Explicit hiring/service requests (r/forhire style)
            "[Hiring] tokenization",
            "[Hiring] RWA developer",
            "[For Hire] blockchain",
            "[Task] smart contract",
            "[Task] tokenization",
            "need developer tokenization",
            "hiring blockchain consultant",
            "looking for RWA developer",
            "need RWA consultant",
            "hiring asset tokenization",
            
            # Tier 2: Help-seeking (casual Reddit language)
            "how do I tokenize",
            "how to tokenize real estate",
            "help with tokenization",
            "tokenization advice",
            "recommend tokenization platform",
            "best way to tokenize assets",
            "anyone know tokenization",
            "fractional ownership platform",
            "how to fractionalize assets",
            "real estate fractionalization",
            
            # Tier 3: Problem statements (implicit need)
            "tokenization too expensive",
            "struggling with asset tokenization",
            "tokenization budget",
            "need simple tokenization",
            "tokenization for small business",
            "affordable asset tokenization",
            "cost effective tokenization",
            
            # Tier 4: Specific Asset Classes (high intent)
            "tokenize real estate",
            "tokenize property",
            "tokenize commodities",
            "tokenize gold",
            "tokenize artwork",
            "tokenize wine",
            "tokenize commercial property",
            "tokenize rental property",
            "property backed tokens",
            "real estate backed tokens",
            
            # Tier 5: Fractional ownership (RWA core use case)
            "fractional real estate",
            "fractional property ownership",
            "fractionalized assets",
            "partial ownership platform",
            "share ownership real estate",
            
            # Tier 6: Broader RWA topics (will catch discussions)
            "real world asset tokenization",
            "RWA platform",
            "tokenized real estate",
            "asset backed tokens",
            "security token offering",
            "STO platform",
            "digital securities",
        ],
        
        # ============================================================
        # LINKEDIN-OPTIMIZED: Professional, job-posting style
        # ============================================================
        'rwa_linkedin': [
            # Strategy: Use single keywords that appear in job posts/requests
            # LinkedIn's literal search means complex phrases backfire
            
            # Core RWA terms (high relevance)
            "tokenization consultant",
            "RWA developer",
            "RWA consultant",
            "asset tokenization expert",
            "blockchain tokenization",
            "real estate tokenization",
            "tokenization specialist",
            "fractional ownership platform",
            
            # Job posting language
            "tokenization position",
            "hiring tokenization",
            "tokenization role",
            "tokenization engineer",
            "tokenization architect",
            "RWA engineer",
            "asset tokenization developer",
            
            # Project-based (catches RFPs/project posts)
            "tokenization project",
            "RWA implementation",
            "tokenization solution",
            "tokenization platform development",
            "asset tokenization initiative",
            "digital asset tokenization",
            "security token project",
            
            # Specific Asset Classes (enterprise signals)
            "real estate tokenization project",
            "property tokenization",
            "commercial real estate tokenization",
            "commodity tokenization",
            "art tokenization",
            "precious metals tokenization",
            
            # Fractional ownership (key RWA use case)
            "fractional ownership",
            "fractionalization platform",
            "fractional real estate",
            "partial ownership solution",
            
            # Security tokens (regulated RWA)
            "security token offering",
            "STO platform",
            "digital securities",
            "tokenized securities",
            "regulated token",
            
            # Budget/commercial signals
            "tokenization RFP",
            "tokenization proposal",
            "tokenization partnership",
            "tokenization vendor",
            "asset tokenization services",
            "tokenization company",
            
            # Enterprise/institutional language
            "institutional tokenization",
            "enterprise tokenization",
            "tokenization compliance",
            "regulated tokenization",
            
            # Avoid: "looking for" (returns "looking back at", "if you're looking for")
            # Avoid: Long phrases (LinkedIn doesn't do semantic search)
        ],
        
      
        # ============================================================
        # UNIVERSAL RWA (works on both, but less optimized)
        # ============================================================
        'rwa': [
            # Conservative keywords that work across platforms
            "tokenization",
            "RWA tokenization",
            "asset tokenization",
            "real world asset",
            "real estate tokenization",
            "property tokenization",
            "tokenization service",
            "blockchain tokenization",
            "tokenization consultant",
            "tokenization platform",
            "tokenization developer",
            "smart contract tokenization",
            "fractional ownership",
            "fractionalized assets",
            "security token",
            "digital securities",
            "tokenized assets",
            "asset backed token",
            "commodity tokenization",
            "STO platform",
            "security token offering",
        ],
        
        # ============================================================
        # CRYPTO SERVICES
        # ============================================================
        'crypto_reddit': [
            "[Hiring] crypto developer",
            "[For Hire] web3",
            "need crypto help",
            "crypto integration advice",
            "recommend crypto developer",
            "web3 developer needed",
            "DeFi help",
            "smart contract audit",
        ],
        
        'crypto_linkedin': [
            "crypto developer position",
            "web3 engineer",
            "DeFi consultant",
            "crypto integration project",
            "blockchain developer hiring",
            "smart contract developer",
            "crypto payment integration",
        ],
        
        'crypto': [
            "crypto developer",
            "web3 consultant",
            "DeFi platform",
            "crypto integration",
            "smart contract developer",
        ],
        
        # ============================================================
        # AI/ML SERVICES
        # ============================================================
        'ai_reddit': [
            "[Hiring] AI developer",
            "[Task] machine learning",
            "need AI help",
            "AI automation advice",
            "recommend AI consultant",
            "chatbot development help",
            "ML model help",
        ],
        
        'ai_linkedin': [
            "AI consultant position",
            "machine learning engineer",
            "AI automation project",
            "chatbot developer",
            "ML engineer hiring",
            "AI integration specialist",
        ],
        
        'ai': [
            "AI consultant",
            "machine learning",
            "AI automation",
            "chatbot development",
            "AI integration",
        ],
        
        # ============================================================
        # BLOCKCHAIN SERVICES
        # ============================================================
        'blockchain_reddit': [
            "[Hiring] blockchain developer",
            "[For Hire] smart contract",
            "need blockchain help",
            "blockchain consultant advice",
            "smart contract audit help",
            "recommend blockchain developer",
        ],
        
        'blockchain_linkedin': [
            "blockchain consultant position",
            "blockchain architect",
            "blockchain developer hiring",
            "smart contract engineer",
            "blockchain integration project",
            "distributed ledger consultant",
        ],
        
        'blockchain': [
            "blockchain consultant",
            "blockchain developer",
            "smart contract",
            "blockchain integration",
            "distributed ledger",
        ],
        
        # ============================================================
        # GENERIC SERVICE-SEEKING (platform-agnostic)
        # ============================================================
        'general': [
            "consultant needed",
            "developer needed",
            "expert needed",
            "service recommendation",
            "platform recommendation",
        ],
    }
    
    # ===================================================================
    # KEYWORD USAGE GUIDE
    # ===================================================================
    # 
    # REDDIT RUNS:
    # python main.py --sources reddit --service rwa_reddit --qualify --max-total-leads 200
    # - Uses Reddit-optimized keywords (casual, forum-style)
    # - Searches r/forhire, r/slavelabour, etc.
    # - Catches "[Hiring]" posts and help-seeking questions
    # 
    # LINKEDIN RUNS:
    # python main.py --sources linkedin_apify --service rwa_linkedin --qualify --max-total-leads 200
    # - Uses LinkedIn-optimized keywords (professional, job-posting style)
    # - Avoids complex phrases that match wrong content
    # - Focuses on job postings and project announcements
    # 
    # BOTH PLATFORMS (TESTING):
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
    max_total_leads: int = 200  # Global limit - stops scraping after this many total leads
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
