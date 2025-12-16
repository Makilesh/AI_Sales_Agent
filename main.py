"""Main entry point for Multi-Source Lead Scraping Engine."""

import argparse
import asyncio
from datetime import datetime
from pathlib import Path

from config.settings import settings
from models.lead import Lead
from scrapers.reddit_scraper import RedditScraper
from scrapers.discord_scraper import DiscordScraper
from scrapers.slack_scraper import SlackScraper
from scrapers.linkedin_public_scraper import LinkedInPublicScraper
from scrapers.linkedin_pw_scraper import LinkedInPlaywrightScraper
from scrapers.linkedin_sl_scraper import LinkedInSeleniumScraper
from storage.json_handler import append_leads, save_leads
from storage.excel_handler import export_to_excel
from utils.linkedin_helpers import get_linkedin_user_agents
from utils.llm_handler import qualify_leads_concurrent, qualify_leads_in_batches


# Module-level counter for LinkedIn public scraper daily limit
_linkedin_public_daily_requests = 0
_linkedin_public_last_reset = datetime.now().date()


async def scrape_reddit() -> list[Lead]:
    """Scrape leads from Reddit."""
    print("\n=== Starting Reddit scraping ===")
    try:
        scraper = RedditScraper(
            client_id=settings.reddit.client_id,
            client_secret=settings.reddit.client_secret,
            user_agent=settings.reddit.user_agent,
            keywords=settings.scraping.keywords,
            subreddits=settings.reddit.subreddits,
            rate_limit=settings.reddit.rate_limit,
            days_filter=settings.scraping.days_filter
        )
        leads = await scraper.scrape_with_rate_limit()
        print(f"✓ Reddit: Found {len(leads)} leads")
        return leads
    except Exception as e:
        print(f"✗ Reddit scraping failed: {e}")
        return []


async def scrape_discord() -> list[Lead]:
    """Scrape leads from Discord."""
    print("\n=== Starting Discord scraping ===")
    try:
        scraper = DiscordScraper(
            bot_token=settings.discord.bot_token,
            keywords=settings.scraping.keywords,
            channel_ids=settings.discord.channels,
            rate_limit=settings.discord.rate_limit,
            days_filter=settings.scraping.days_filter
        )
        leads = await scraper.scrape_with_rate_limit()
        print(f"✓ Discord: Found {len(leads)} leads")
        return leads
    except Exception as e:
        print(f"✗ Discord scraping failed: {e}")
        return []


async def scrape_slack() -> list[Lead]:
    """Scrape leads from Slack."""
    print("\n=== Starting Slack scraping ===")
    try:
        scraper = SlackScraper(
            bot_token=settings.slack.bot_token,
            keywords=settings.scraping.keywords,
            channel_ids=settings.slack.channels,
            rate_limit=settings.slack.rate_limit,
            days_filter=settings.scraping.days_filter
        )
        leads = await scraper.scrape_with_rate_limit()
        print(f"✓ Slack: Found {len(leads)} leads")
        return leads
    except Exception as e:
        print(f"✗ Slack scraping failed: {e}")
        return []


async def scrape_linkedin_public() -> list[Lead]:
    """EXPERIMENTAL: Scrape LinkedIn public search (Phase 1.1 lead discovery)."""
    global _linkedin_public_daily_requests, _linkedin_public_last_reset
    
    if not settings.linkedin_public.enabled:
        return []
    
    # Reset daily counter
    today = datetime.now().date()
    if today > _linkedin_public_last_reset:
        _linkedin_public_daily_requests = 0
        _linkedin_public_last_reset = today
    
    # Check daily limit
    if _linkedin_public_daily_requests >= settings.linkedin_public.max_daily_requests:
        print(f"⚠️  LinkedIn Public: Daily limit reached ({settings.linkedin_public.max_daily_requests}). Skipping.")
        return []
    
    print("\n=== EXPERIMENTAL: LinkedIn Public Scraping ===")
    try:
        scraper = LinkedInPublicScraper(
            keywords=settings.scraping.keywords[:3],  # Limit to 3 keywords
            user_agents=get_linkedin_user_agents(),
            rate_limit=settings.linkedin_public.rate_limit
        )
        leads = await scraper.scrape_with_rate_limit()
        _linkedin_public_daily_requests += len(settings.scraping.keywords[:3])
        
        print(f"✓ LinkedIn Public: Found {len(leads)} leads ({_linkedin_public_daily_requests}/{settings.linkedin_public.max_daily_requests} daily)")
        return leads
    except Exception as e:
        print(f"✗ LinkedIn Public failed: {e}")
        return []


async def scrape_linkedin_public() -> list[Lead]:
    """Scrape LinkedIn using free public scraper (no authentication required)."""
    if not settings.linkedin_apify.enabled:
        return []
    
    print("\n=== Starting LinkedIn Public Scraping ===")
    try:
        scraper = LinkedInPublicScraper(
            keywords=settings.scraping.keywords,
            max_posts_per_keyword=settings.linkedin_apify.max_posts_per_keyword,
            max_total_leads=settings.scraping.max_total_leads,
            days_filter=settings.linkedin_apify.days_filter,
            min_reactions=settings.linkedin_apify.min_reactions,
            rate_limit=2  # 2 seconds between requests
        )
        leads = await scraper.scrape_with_rate_limit()
        print(f"✓ LinkedIn Public scraping complete: {len(leads)} leads found")
        return leads
    except Exception as e:
        print(f"❌ LinkedIn Public scraping failed: {e}")
        return []


async def scrape_linkedin_apify() -> list[Lead]:
    """Scrape LinkedIn using Apify API (paid service)"""
    if not settings.linkedin_apify.apify_token:
        print("LinkedIn Apify: Token not configured, skipping")
        return []
    
    print("\n=== Starting LinkedIn Apify Scraping ===")
    try:
        scraper = LinkedInApifyScraper(
            apify_token=settings.linkedin_apify.apify_token,
            keywords=settings.scraping.keywords,
            max_posts_per_keyword=settings.linkedin_apify.max_posts_per_keyword,
            rate_limit=settings.linkedin_apify.rate_limit,
            actor_id=settings.linkedin_apify.actor_id,
            linkedin_cookie=settings.linkedin_apify.linkedin_cookie,
            proxy_config=settings.linkedin_apify.proxy_config,
            scrape_posts=settings.linkedin_apify.scrape_posts,
            scrape_articles=settings.linkedin_apify.scrape_articles,
            scrape_discussions=settings.linkedin_apify.scrape_discussions,
            scrape_comments=settings.linkedin_apify.scrape_comments,
            scrape_reactions=settings.linkedin_apify.scrape_reactions,
            only_posts=settings.linkedin_apify.only_posts,
            include_sponsored=settings.linkedin_apify.include_sponsored,
            min_reactions=settings.linkedin_apify.min_reactions,
            max_total_leads=settings.scraping.max_total_leads,
            days_filter=settings.linkedin_apify.days_filter
        )
        leads = await scraper.scrape_with_rate_limit()
        print(f"✓ LinkedIn Apify: Found {len(leads)} leads")
        return leads
    except Exception as e:
        print(f"✗ LinkedIn Apify failed: {e}")
        return []


async def scrape_linkedin_playwright() -> list[Lead]:
    """Scrape LinkedIn using Playwright browser automation."""
    if not settings.linkedin_cookie:
        print("LinkedIn Playwright: Cookie not configured, skipping")
        return []
    
    print("\n=== Starting LinkedIn Playwright Scraping ===")
    # Get headless setting from command line args or default to False for debugging
    headless_mode = getattr(main, '_headless_arg', False)
    if not headless_mode:
        print("  ℹ️  Running in VISIBLE mode for debugging. Use --headless to run hidden.")
    try:
        scraper = LinkedInPlaywrightScraper(
            linkedin_cookie=settings.linkedin_cookie,
            keywords=settings.scraping.keywords,
            max_posts_per_keyword=settings.linkedin_apify.max_posts_per_keyword,
            max_total_leads=settings.scraping.max_total_leads,
            rate_limit=10,  # 10 requests per minute
            headless=headless_mode,
            days_filter=settings.linkedin_apify.days_filter,
            proxy=settings.linkedin_proxy if hasattr(settings, 'linkedin_proxy') else None
        )
        leads = await scraper.scrape()
        print(f"✓ LinkedIn Playwright scraping complete: {len(leads)} leads found")
        return leads
    except Exception as e:
        print(f"❌ LinkedIn Playwright scraping failed: {e}")
        return []


async def scrape_linkedin_selenium() -> list[Lead]:
    """Scrape LinkedIn using Selenium WebDriver."""
    if not settings.linkedin_cookie:
        print("LinkedIn Selenium: Cookie not configured, skipping")
        return []
    
    print("\n=== Starting LinkedIn Selenium Scraping ===")
    # Get headless setting from command line args or default to False for debugging
    headless_mode = getattr(main, '_headless_arg', False)
    if not headless_mode:
        print("  ℹ️  Running in VISIBLE mode for debugging. Use --headless to run hidden.")
    try:
        # Run synchronously (Selenium is not async)
        scraper = LinkedInSeleniumScraper(
            linkedin_cookie=settings.linkedin_cookie,
            keywords=settings.scraping.keywords,
            max_posts_per_keyword=settings.linkedin_apify.max_posts_per_keyword,
            max_total_leads=settings.scraping.max_total_leads,
            rate_limit=10,  # 10 requests per minute
            headless=headless_mode,
            days_filter=settings.linkedin_apify.days_filter,
            proxy=settings.linkedin_proxy if hasattr(settings, 'linkedin_proxy') else None
        )
        leads = scraper.scrape()
        print(f"✓ LinkedIn Selenium scraping complete: {len(leads)} leads found")
        return leads
    except Exception as e:
        print(f"❌ LinkedIn Selenium scraping failed: {e}")
        return []


async def scrape_linkedin_selenium() -> list[Lead]:
    """Scrape LinkedIn using Selenium WebDriver."""
    if not settings.linkedin_cookie:
        print("LinkedIn Selenium: Cookie not configured, skipping")
        return []
    
    print("\n=== Starting LinkedIn Selenium Scraping ===")
    # Get headless setting from command line args or default to False for debugging
    headless_mode = getattr(main, '_headless_arg', False)
    if not headless_mode:
        print("  ℹ️  Running in VISIBLE mode for debugging. Use --headless to run hidden.")
    try:
        # Run synchronously (Selenium is not async)
        scraper = LinkedInSeleniumScraper(
            linkedin_cookie=settings.linkedin_cookie,
            keywords=settings.scraping.keywords,
            max_posts_per_keyword=settings.linkedin_apify.max_posts_per_keyword,
            max_total_leads=settings.scraping.max_total_leads,
            rate_limit=10,  # 10 requests per minute
            headless=headless_mode,
            days_filter=settings.linkedin_apify.days_filter,
            proxy=settings.linkedin_proxy if hasattr(settings, 'linkedin_proxy') else None
        )
        leads = scraper.scrape()
        print(f"✓ LinkedIn Selenium scraping complete: {len(leads)} leads found")
        return leads
    except Exception as e:
        print(f"❌ LinkedIn Selenium scraping failed: {e}")
        return []


async def run_scrapers(sources: list[str]) -> list[Lead]:
    """Run specified scrapers concurrently."""
    tasks = []
    
    if 'reddit' in sources:
        tasks.append(scrape_reddit())
    
    if 'discord' in sources:
        tasks.append(scrape_discord())
    
    if 'slack' in sources:
        tasks.append(scrape_slack())
    
    if 'linkedin_public' in sources or 'linkedin' in sources:
        tasks.append(scrape_linkedin_public())
    
    if 'linkedin_apify' in sources:
        tasks.append(scrape_linkedin_apify())
    
    if 'linkedin_pw' in sources:
        tasks.append(scrape_linkedin_playwright())
    
    if 'linkedin_selenium' in sources or 'linkedin_sl' in sources:
        tasks.append(scrape_linkedin_selenium())
    
    if not tasks:
        print("No valid sources specified")
        return []
    
    # Run all scrapers concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Flatten results and filter out errors
    all_leads = []
    for result in results:
        if isinstance(result, list):
            all_leads.extend(result)
        elif isinstance(result, Exception):
            print(f"Scraper error: {result}")
    
    return all_leads


def filter_qualified_leads(leads: list[Lead]) -> list[Lead]:
    """Filter leads based on qualification criteria."""
    qualified = [
        lead for lead in leads 
        if lead.is_qualified(min_engagement=settings.scraping.min_engagement_score)
    ]
    print(f"\nFiltered to {len(qualified)} qualified leads (from {len(leads)} total)")
    return qualified


def main():
    """Main execution function."""
    # Initialize headless attribute for use in async functions
    main._headless_arg = False
    
    parser = argparse.ArgumentParser(
        description="Multi-Source Lead Scraping Engine - Phase 1"
    )
    parser.add_argument(
        '--sources',
        nargs='+',
        choices=['reddit', 'discord', 'slack', 'linkedin', 'linkedin_public', 'linkedin_apify', 'linkedin_pw', 'linkedin_selenium', 'linkedin_sl'],
        default=['reddit', 'discord', 'slack'],
        help='Sources to scrape (linkedin=free public, linkedin_public=free, linkedin_apify=paid, linkedin_pw=playwright, linkedin_selenium/linkedin_sl=selenium)'
    )
    parser.add_argument(
        '--service',
        type=str,
        choices=[
            # OPTIMIZED: Cross-platform presets (8 total, no platform variants)
            'competitor_frustration', 'rwa', 'crypto', 'ai',
            'blockchain', 'web3', 'defi', 'smart_contracts'
        ],
        help='OPTIMIZED: Service inquiry type (cross-platform). Options: competitor_frustration, rwa, crypto, ai, blockchain, web3, defi, smart_contracts'
    )
    parser.add_argument(
        '--max-total-leads',
        type=int,
        help='Global limit - stop after this many leads (default: 500, optimized from 200)'
    )
    parser.add_argument(
        '--days-filter',
        type=int,
        help='Only include content from last N days (default: 30 days, 0 = no filter)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='data/leads.json',
        help='Output file path (default: data/leads.json)'
    )
    parser.add_argument(
        '--no-filter',
        action='store_true',
        help='Skip lead qualification filtering'
    )
    parser.add_argument(
        '--qualify',
        action='store_true',
        help='Automatically qualify leads with LLM (no prompt)'
    )
    parser.add_argument(
        '--filter-service',
        type=str,
        choices=['RWA', 'Crypto', 'AI/ML', 'Blockchain', 'Web3'],
        help='LLM filter: ONLY qualify leads asking for specific service (RWA, Crypto, AI/ML, Blockchain, Web3)'
    )
    parser.add_argument(
        '--min-confidence',
        type=float,
        default=0.65,
        help='OPTIMIZED: Minimum confidence score for qualified leads (0.0-1.0, default: 0.65, increased from 0.6). Leads below this are filtered out.'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='OPTIMIZED: Process leads in batches of N (default: 100, increased from 50). Enables progressive saving and cost tracking.'
    )
    parser.add_argument(
        '--llm-batch-size',
        type=int,
        default=20,
        help='OPTIMIZED: Number of leads to send to LLM in single API call (default: 20, increased from 10). Higher = better consistency, lower cost.'
    )
    parser.add_argument(
        '--headless',
        action='store_true',
        help='Run Playwright browser in headless mode (default: visible for debugging)'
    )
    parser.add_argument(
        '--export-all-leads',
        action='store_true',
        help='Export all scraped leads (qualified + unqualified) to separate Excel file. Default: only export qualified leads.'
    )

    args = parser.parse_args()
    
    # Apply service preset if specified
    if args.service:
        preset_keywords = settings.scraping.KEYWORD_PRESETS.get(args.service, [])
        if preset_keywords:
            settings.scraping.keywords = preset_keywords
            print(f"🎯 Using '{args.service}' keyword preset ({len(preset_keywords)} keywords)")
        else:
            print(f"⚠️  Service preset '{args.service}' not found, using default keywords")
        
        # 🔍 NEW: Filter subreddits based on service type
        service_subreddits = settings.reddit.SERVICE_SUBREDDITS.get(args.service, [])
        if service_subreddits and 'reddit' in args.sources:
            original_count = len(settings.reddit.subreddits)
            settings.reddit.subreddits = service_subreddits
            print(f"📊 Filtered subreddits: {len(service_subreddits)} relevant to {args.service.upper()} (was {original_count})")
    
    # Apply global limit if specified
    if args.max_total_leads:
        settings.scraping.max_total_leads = args.max_total_leads
    
    # Apply days filter if specified
    if args.days_filter is not None:
        settings.scraping.days_filter = args.days_filter
    
    print("=" * 60)
    print("Multi-Source Lead Scraping Engine - Phase 1")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Sources: {', '.join(args.sources)}")
    print(f"Keywords: {len(settings.scraping.keywords)}")
    if args.service:
        print(f"Service Type: {args.service.upper()}")
    if args.filter_service:
        print(f"🎯 LLM Filter: {args.filter_service} leads only")
    print(f"Max Total Leads: {settings.scraping.max_total_leads}")
    print(f"Output: {args.output}")
    
    # Validate settings
    if not settings.validate():
        print("\nWarning: Some credentials are missing. Scrapers may fail.")
    
    # Store headless argument for use in scrape functions
    main._headless_arg = args.headless
    
    try:
        # Run scrapers
        leads = asyncio.run(run_scrapers(args.sources))
        
        if not leads:
            print("\n✗ No leads found")
            return
        
        # Filter qualified leads
        if not args.no_filter:
            leads = filter_qualified_leads(leads)
        
        # Save leads to JSON BEFORE LLM qualification
        # This ensures we have all scraped data even if LLM fails
        print(f"\n💾 Saving {len(leads)} leads to {args.output}...")
        append_leads(leads, args.output)
        print(f"   ✓ Saved to {args.output} (deduped by URL)")

        # OPTIONAL: Export all leads to Excel (only if --export-all-leads flag is set)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        unqualified_leads_excel = None
        if args.export_all_leads:
            unqualified_leads_excel = f"data/unqualified_leads_{timestamp_str}.xlsx"
            print(f"\n📊 Exporting all {len(leads)} scraped leads to Excel (qualified + unqualified)...")
            from storage.excel_handler import export_all_leads_to_excel
            export_all_leads_to_excel(leads, unqualified_leads_excel)
        
        # LLM qualification (auto or prompt based on settings)
        should_qualify = args.qualify or (settings.openai_api_key and not args.qualify)
        
        if should_qualify:
            if not args.qualify and settings.openai_api_key:
                # Prompt user if not auto-enabled but API key exists
                print("\n" + "=" * 60)
                llm_choice = input("Qualify leads with LLM? (y/n): ").strip().lower()
                should_qualify = llm_choice == 'y'
            
            if should_qualify:
                try:
                    # IMPROVED: Use batch processing with progressive saving
                    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                    all_qualifications = []  # Track qualifications as we go

                    # Progress callback for saving after each batch
                    def save_batch_progress(batch_num, total_batches, batch_results, stats):
                        """Save qualified leads after each batch for crash recovery."""
                        # Add batch results to cumulative list
                        all_qualifications.extend(batch_results)

                        # Get leads processed so far
                        end_idx = len(all_qualifications)
                        processed_leads = leads[:end_idx]

                        # Filter to qualified with min confidence
                        qualified_batch = [
                            (lead, qual)
                            for lead, qual in zip(processed_leads, all_qualifications)
                            if qual.get('is_qualified', False) and qual.get('confidence_score', 0.0) >= args.min_confidence
                        ]

                        if qualified_batch:
                            qualified_leads_batch, qualified_quals_batch = zip(*qualified_batch)

                            # Save cumulative results after this batch
                            if args.filter_service:
                                progress_filename = f"data/qualified_leads_{args.filter_service.lower()}_progress_{timestamp_str}.xlsx"
                            else:
                                progress_filename = f"data/qualified_leads_progress_{timestamp_str}.xlsx"

                            export_to_excel(list(qualified_leads_batch), list(qualified_quals_batch), progress_filename)
                            print(f"   💾 Progress saved ({stats['total_qualified']}/{stats['total_processed']} qualified)")

                    if args.filter_service:
                        print(f"   🎯 Filtering for: {args.filter_service} service leads")

                    # Use batch processing (progressive saving + cost tracking + LLM-side batching)
                    qualifications = asyncio.run(qualify_leads_in_batches(
                        leads,
                        batch_size=args.batch_size,
                        max_concurrent=settings.max_concurrent_llm_requests,
                        llm_batch_size=args.llm_batch_size,  # NEW: LLM-side batching for better consistency
                        target_service=args.filter_service,
                        progress_callback=save_batch_progress
                    ))
                    
                    # Add qualification results back to lead objects
                    for lead, qual in zip(leads, qualifications):
                        lead.qualification_result = qual
                    
                    # IMPROVED: Filter to qualified leads with minimum confidence threshold
                    min_confidence = args.min_confidence
                    qualified_results = [
                        (lead, qual)
                        for lead, qual in zip(leads, qualifications)
                        if qual.get('is_qualified', False) and qual.get('confidence_score', 0.0) >= min_confidence
                    ]

                    # Count low-confidence leads that were filtered out
                    low_confidence_count = sum(
                        1 for qual in qualifications
                        if qual.get('is_qualified', False) and qual.get('confidence_score', 0.0) < min_confidence
                    )
                    
                    if qualified_results:
                        qualified_leads, qualified_quals = zip(*qualified_results)
                        
                        # Calculate qualification rate
                        total_leads = len(leads)
                        qualified_count = len(qualified_leads)
                        qualification_rate = (qualified_count / total_leads * 100) if total_leads > 0 else 0
                        
                        # Export to Excel with timestamp to avoid permission conflicts
                        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                        if args.filter_service:
                            excel_filename = f"data/qualified_leads_{args.filter_service.lower()}_{timestamp_str}.xlsx"
                        else:
                            excel_filename = f"data/qualified_leads_{timestamp_str}.xlsx"
                        print(f"\n📊 Exporting qualified leads to {excel_filename}...")
                        export_to_excel(list(qualified_leads), list(qualified_quals), excel_filename)
                        
                        # Print summary
                        print("\n" + "=" * 60)
                        print("LLM QUALIFICATION SUMMARY")
                        print("=" * 60)
                        print(f"📄 All leads JSON: {args.output}")
                        if unqualified_leads_excel:
                            print(f"📄 Unqualified leads Excel: {unqualified_leads_excel}")
                        if args.filter_service:
                            print(f"🎯 Service Filter: {args.filter_service}")
                        print(f"✅ {qualified_count}/{total_leads} leads qualified ({qualification_rate:.1f}% qualification rate)")
                        if low_confidence_count > 0:
                            print(f"⚠️  {low_confidence_count} leads filtered out (confidence < {min_confidence})")
                        print(f"📄 Qualified leads Excel: {excel_filename}")
                    else:
                        print("\n⚠️  No leads were qualified by the LLM")
                        if args.filter_service:
                            print(f"    (No leads found asking for {args.filter_service} services)")
                        print(f"📄 All scraped leads are still available in JSON: {args.output}")
                        if unqualified_leads_excel:
                            print(f"📄 Unqualified leads Excel: {unqualified_leads_excel}")
                        
                except Exception as e:
                    print(f"\n⚠️  LLM qualification failed: {e}")
                    print("Continuing without LLM qualification...")
        
        # Save leads again with qualification results (updates the file)
        # This ensures qualification_result field is persisted
        if should_qualify:
            print(f"\n💾 Updating leads with qualification results in {args.output}...")
            append_leads(leads, args.output)
            print(f"   ✓ Updated {len(leads)} leads with qualification data")
        
        print("\n" + "=" * 60)
        print(f"✓ Successfully scraped {len(leads)} leads")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user")
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        if settings.debug_mode:
            raise


if __name__ == "__main__":
    main()
