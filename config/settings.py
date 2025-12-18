

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
    
    # Service-specific subreddit mappings
    SERVICE_SUBREDDITS: dict[str, list[str]] = field(default_factory=lambda: {
        "rwa": [
            # Business/entrepreneur subreddits (people seeking solutions)
            "entrepreneur", "startups", "smallbusiness", "SaaS",
            # Real estate focused (high RWA relevance)
            "realestateinvesting", "RealEstate", "CommercialRealEstate", 
            "RealEstateInvestments", "investing",
            # Tokenization specific
            "tokenization", "SecurityTokens", "assetmanagement",
            # DeFi/Web3 (for RWA tokenization projects)
            "defi", "web3",
        ],
        "crypto": [
            # Business seeking crypto solutions
            "entrepreneur", "startups", "smallbusiness",
            # Crypto/Web3 focused
            "cryptocurrency", "CryptoTechnology", "web3", "defi",
            "ethdev", "solidity", "cryptodevs",
            # Crypto jobs/gigs
            "Jobs4Bitcoins",
        ],
        "ai": [
            # Business seeking AI solutions
            "entrepreneur", "startups", "smallbusiness", "SaaS",
            # AI/ML focused
            "learnmachinelearning",
        ],
        "blockchain": [
            # Business seeking blockchain solutions
            "entrepreneur", "startups", "smallbusiness",
            # Blockchain focused
            "cryptocurrency", "CryptoTechnology", "web3", "defi",
            "ethdev", "solidity", "cryptodevs",
        ],
        "web3": [
            # Business seeking Web3 solutions
            "entrepreneur", "startups", "smallbusiness", "SaaS",
            # Web3 focused
            "web3", "cryptocurrency", "defi", "ethdev",
        ],
        "defi": [
            # Business seeking DeFi solutions
            "entrepreneur", "startups", "smallbusiness",
            # DeFi focused
            "defi", "cryptocurrency", "CryptoTechnology", "web3",
        ],
        "smart_contracts": [
            # Business seeking smart contract solutions
            "entrepreneur", "startups", "smallbusiness",
            # Smart contract focused
            "ethdev", "solidity", "web3", "cryptocurrency",
        ],
    })


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
    # Use --service flag: python main.py --sources reddit --service rwa
    #                or: python main.py --sources linkedin_apify --service rwa_linkedin
    
    # REDDIT BEHAVIOR:
    # - Searches post titles AND content
    # - Casual/informal language
    # - Mix of questions, advice-seeking, hiring posts
    # - Best in r/forhire, r/slavelabour (explicit gig posts)
    
    # LINKEDIN BEHAVIOR:
    # - Searches post content (literal keyword matching)
    # - Professional/corporate language
    # - B2B focused, decision-maker posts
    # - Industry terminology, regulatory compliance mentions
    # - Company announcements, professional pain points
    
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
        # REDDIT PRESETS (Casual, Help-Seeking Language)
        # ============================================================

        # 1. COMPETITOR FRUSTRATION (Reddit)
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
        
        # 2. RWA TOKENIZATION (Reddit - Casual Language)
        'rwa': [
            # EXPLICIT ASSET OWNER INTENT
            "tokenize my property", "tokenize our assets", "tokenize my real estate",
            "fractional ownership for my", "fractionalize my property",
            "tokenize my portfolio", "tokenize our portfolio", "tokenize my fund",
            
            # EXPLORATORY/RESEARCH
            "how to tokenize real estate", "how to tokenize assets", "how to tokenize property",
            "how to fractionalize", "exploring tokenization", "considering tokenization",
            
            # DIRECT SERVICE SEEKING
            "need asset tokenization", "need tokenization platform", "need to tokenize",
            "looking for tokenization platform", "seeking tokenization service",
            "want to tokenize", "tokenization consultant", "tokenization service",
            
            # PLATFORM SPECIFIC
            "property tokenization service", "real estate fractionalization",
            "tokenization platform", "asset tokenization platform",
            "fractional real estate platform", "real estate token platform",
            
            # NATURAL LANGUAGE
            "tokenize real estate", "tokenize property", "tokenize assets",
            "fractional real estate", "fractional ownership", "fractionalize property",
            "blockchain real estate", "crypto real estate"
        ],
        
        # 3. CRYPTO/WEB3 (Reddit)
        'crypto': [
            "crypto developer", "web3 consultant", "DeFi platform",
            "crypto integration", "smart contract developer", "web3 engineer",
            "DeFi consultant", "crypto payment", "blockchain developer",
            "need crypto help", "hiring crypto", "web3 project",
            "crypto consultant", "web3 agency", "crypto services"
        ],

        # 4. AI/ML (Reddit)
        'ai': [
            "AI consultant", "machine learning engineer", "AI automation",
            "chatbot development", "AI integration", "ML model",
            "AI developer", "chatbot developer", "ML engineer",
            "need AI help", "hiring AI", "AI project",
            "machine learning consultant", "AI services"
        ],

        # 5. BLOCKCHAIN (Reddit)
        'blockchain': [
            "blockchain consultant", "blockchain developer", "smart contract",
            "blockchain integration", "distributed ledger", "blockchain architect",
            "blockchain project", "need blockchain help", "hiring blockchain",
            "blockchain solution", "smart contract audit", "blockchain platform"
        ],

        # 6. WEB3 (Reddit)
        'web3': [
            "web3 developer", "web3 consultant", "web3 platform",
            "web3 integration", "web3 project", "decentralized app",
            "dApp developer", "web3 solution", "need web3 help",
            "hiring web3", "web3 specialist", "web3 service"
        ],

        # 7. DEFI (Reddit)
        'defi': [
            "DeFi developer", "DeFi consultant", "DeFi platform",
            "DeFi protocol", "DeFi integration", "DeFi project",
            "liquidity pool", "yield farming", "staking platform",
            "DEX development", "need DeFi help", "hiring DeFi"
        ],

        # 8. SMART CONTRACTS (Reddit)
        'smart_contracts': [
            "smart contract developer", "smart contract audit", "Solidity developer",
            "smart contract engineer", "contract security", "Ethereum developer",
            "smart contract consultant", "need smart contract", "hiring solidity",
            "smart contract review", "contract audit"
        ],

        # ============================================================
        # LINKEDIN PRESETS (Professional B2B Language)
        # ============================================================

        # 9. COMPETITOR FRUSTRATION (LinkedIn - Professional)
        'competitor_frustration_linkedin': [
            "seeking alternative to current tokenization provider",
            "evaluating new blockchain development partners",
            "looking for reliable RWA tokenization solution",
            "disappointed with existing Web3 vendor",
            "transition from current digital asset platform",
            "seeking experienced tokenization consultants",
            "need enterprise-grade blockchain solution",
            "comparing tokenization service providers",
            "looking for cost-effective RWA solutions",
            "require better smart contract development partner",
            "seeking professional blockchain consulting firm",
            "need scalable tokenization infrastructure",
            "looking for compliant digital securities platform",
            "seeking regulatory-compliant tokenization solution",
            "evaluating blockchain technology partners"
        ],

        # 10. RWA TOKENIZATION (LinkedIn - Corporate/Professional)
        # HIGHLY TARGETED: Asset managers, fund managers, real estate professionals
        'rwa_linkedin': [
            # EXPLICIT CORPORATE INTENT (C-level, fund managers, asset managers)
            "seeking tokenization solution for our portfolio",
            "exploring asset tokenization for institutional clients",
            "digital transformation of real estate assets",
            "tokenization strategy for commercial real estate",
            "fractional ownership platform for investors",
            "blockchain infrastructure for asset management",
            "security token offering preparation",
            "compliant tokenization of alternative assets",
            
            # PROFESSIONAL SERVICE SEEKING
            "partnering with tokenization technology provider",
            "RWA tokenization consulting engagement",
            "enterprise asset tokenization platform",
            "institutional-grade tokenization solution",
            "blockchain integration for asset management firm",
            "tokenization service provider for fund management",
            
            # INDUSTRY-SPECIFIC (Real Estate, Private Equity, Asset Management)
            "real estate investment tokenization",
            "commercial property fractionalization",
            "private equity token offering",
            "fund tokenization infrastructure",
            "alternative asset digitalization",
            "property token issuance platform",
            
            # REGULATORY/COMPLIANCE (Sophisticated buyers)
            "SEC-compliant tokenization platform",
            "Reg D digital securities offering",
            "Reg A+ tokenization services",
            "accredited investor token platform",
            "security token compliance solution",
            "regulated digital asset issuance",
            
            # INDUSTRY PAIN POINTS
            "modernizing asset distribution",
            "reducing capital formation costs",
            "improving asset liquidity through blockchain",
            "streamlining investor onboarding",
            "automating compliance for digital securities",
            "democratizing access to alternative investments",
            
            # TECHNOLOGY EVALUATION
            "blockchain technology for asset tokenization",
            "smart contract platform for securities",
            "distributed ledger for real estate",
            "tokenization technology stack",
            "digital asset management infrastructure",
            
            # STRATEGIC INITIATIVES
            "digital assets transformation program",
            "blockchain adoption for asset management",
            "tokenization pilot program",
            "exploring RWA market opportunities",
            "building digital securities platform",
            "launching tokenized investment products"
        ],

        # 11. CRYPTO/WEB3 (LinkedIn - Enterprise)
        'crypto_linkedin': [
            "enterprise blockchain development partner",
            "Web3 technology integration for business",
            "corporate crypto payment solutions",
            "institutional DeFi platform development",
            "blockchain consulting for enterprises",
            "Web3 strategy and implementation",
            "crypto treasury management solutions",
            "blockchain infrastructure for finance",
            "enterprise smart contract development",
            "Web3 digital transformation services",
            "cryptocurrency integration partner",
            "decentralized finance for institutions",
            "blockchain architecture consulting",
            "Web3 application development agency",
            "enterprise crypto custody solutions"
        ],

        # 12. AI/ML (LinkedIn - Enterprise)
        'ai_linkedin': [
            "AI transformation consulting engagement",
            "machine learning implementation partner",
            "enterprise AI automation solutions",
            "artificial intelligence strategy consulting",
            "ML model deployment for business",
            "AI-powered business intelligence platform",
            "predictive analytics implementation",
            "natural language processing solutions",
            "computer vision integration services",
            "AI operations and MLOps consulting",
            "generative AI implementation partner",
            "enterprise chatbot development",
            "AI integration for financial services",
            "machine learning infrastructure consulting",
            "intelligent automation solutions"
        ],

        # 13. BLOCKCHAIN (LinkedIn - Enterprise)
        'blockchain_linkedin': [
            "enterprise blockchain implementation",
            "distributed ledger technology consulting",
            "blockchain architecture for business",
            "supply chain blockchain solutions",
            "permissioned blockchain development",
            "enterprise smart contract platform",
            "blockchain integration consulting firm",
            "Hyperledger implementation partner",
            "private blockchain infrastructure",
            "blockchain for trade finance",
            "consortium blockchain development",
            "blockchain scalability solutions",
            "enterprise DLT consulting",
            "blockchain interoperability services",
            "digital identity blockchain solution"
        ],

        # 14. WEB3 (LinkedIn - Corporate)
        'web3_linkedin': [
            "Web3 transformation consulting",
            "decentralized application development partner",
            "Web3 infrastructure consulting",
            "dApp development for enterprises",
            "Web3 product development agency",
            "decentralized technology integration",
            "Web3 architecture consulting",
            "NFT platform development services",
            "metaverse development solutions",
            "Web3 gaming infrastructure",
            "decentralized identity solutions",
            "Web3 marketplace development",
            "IPFS integration services",
            "Web3 authentication solutions",
            "decentralized storage implementation"
        ],

        # 15. DEFI (LinkedIn - Institutional)
        'defi_linkedin': [
            "institutional DeFi solutions",
            "decentralized finance protocol development",
            "DeFi lending platform development",
            "liquidity pool infrastructure",
            "automated market maker development",
            "DeFi yield optimization platform",
            "decentralized exchange development",
            "DeFi risk management solutions",
            "institutional staking infrastructure",
            "DeFi compliance and regulatory solutions",
            "cross-chain DeFi integration",
            "DeFi treasury management",
            "institutional DeFi custody solutions",
            "DeFi derivatives platform development",
            "decentralized credit protocol"
        ],

        # 16. SMART CONTRACTS (LinkedIn - Professional)
        'smart_contracts_linkedin': [
            "enterprise smart contract development",
            "smart contract security audit services",
            "Solidity development consulting",
            "smart contract architecture design",
            "formal verification of smart contracts",
            "smart contract testing framework",
            "upgradeable smart contract development",
            "gas optimization consulting",
            "multi-signature contract development",
            "oracle integration for smart contracts",
            "smart contract monitoring solutions",
            "Ethereum Layer 2 smart contracts",
            "cross-chain smart contract development",
            "smart contract governance implementation",
            "automated smart contract deployment"
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
