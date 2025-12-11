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
from scrapers.linkedin_apify_scraper import LinkedInApifyScraper
from storage.json_handler import append_leads, save_leads
from storage.excel_handler import export_to_excel
from utils.linkedin_helpers import get_linkedin_user_agents
from utils.llm_handler import qualify_leads_concurrent


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
            rate_limit=settings.reddit.rate_limit
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
            rate_limit=settings.discord.rate_limit
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
            rate_limit=settings.slack.rate_limit
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


async def scrape_linkedin_apify() -> list[Lead]:
    """Scrape LinkedIn for people explicitly ASKING for our services (consultants, solutions, platforms)."""
    if not settings.linkedin_apify.enabled:
        return []
    
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
            max_total_leads=settings.scraping.max_total_leads  # Pass global limit
        )
        leads = await scraper.scrape_with_rate_limit()
        print(f"✓ LinkedIn Apify: Found {len(leads)} leads")
        return leads
    except Exception as e:
        print(f"✗ LinkedIn Apify failed: {e}")
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
    
    if 'linkedin_public' in sources and settings.linkedin_public.enabled:
        tasks.append(scrape_linkedin_public())
    
    if 'linkedin_apify' in sources and settings.linkedin_apify.enabled:
        tasks.append(scrape_linkedin_apify())
    
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
    parser = argparse.ArgumentParser(
        description="Multi-Source Lead Scraping Engine - Phase 1"
    )
    parser.add_argument(
        '--sources',
        nargs='+',
        choices=['reddit', 'discord', 'slack', 'linkedin_public', 'linkedin_apify'],
        default=['reddit', 'discord', 'slack'],
        help='Sources to scrape (default: reddit, discord, slack)'
    )
    parser.add_argument(
        '--service',
        type=str,
        choices=[
            # Platform-specific presets (optimized for Reddit or LinkedIn)
            'rwa_reddit', 'rwa_linkedin', 
            'crypto_reddit', 'crypto_linkedin',
            'ai_reddit', 'ai_linkedin',
            'blockchain_reddit', 'blockchain_linkedin',
            # Competitor frustration presets
            'competitor_frustration_reddit', 'competitor_frustration_linkedin',
            # Universal presets (work on both platforms)
            'rwa', 'crypto', 'ai', 'blockchain', 'general', 'all'
        ],
        help='Service inquiry type. Platform-specific: rwa_reddit, rwa_linkedin, etc. Competitor frustration: competitor_frustration_reddit/linkedin. Universal: rwa, crypto, ai, blockchain, general, all'
    )
    parser.add_argument(
        '--max-total-leads',
        type=int,
        help='Global limit - stop after this many leads (default: 200)'
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
    
    args = parser.parse_args()
    
    # Apply service preset if specified
    if args.service:
        preset_keywords = settings.scraping.KEYWORD_PRESETS.get(args.service, [])
        if preset_keywords:
            settings.scraping.keywords = preset_keywords
            print(f"🎯 Using '{args.service}' keyword preset ({len(preset_keywords)} keywords)")
        else:
            print(f"⚠️  Service preset '{args.service}' not found, using default keywords")
    
    # Apply global limit if specified
    if args.max_total_leads:
        settings.scraping.max_total_leads = args.max_total_leads
    
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
        
        # ALWAYS export all leads to Excel (regardless of qualification)
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        all_leads_excel = f"data/all_leads_{timestamp_str}.xlsx"
        print(f"\n📊 Exporting all {len(leads)} leads to Excel...")
        from storage.excel_handler import export_all_leads_to_excel
        export_all_leads_to_excel(leads, all_leads_excel)
        
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
                    print("\n🤖 Starting concurrent LLM qualification...")
                    print(f"   Max concurrent requests: {settings.max_concurrent_llm_requests}")
                    if args.filter_service:
                        print(f"   🎯 Filtering for: {args.filter_service} service leads")
                    
                    qualifications = asyncio.run(qualify_leads_concurrent(
                        leads,
                        max_concurrent=settings.max_concurrent_llm_requests,
                        target_service=args.filter_service
                    ))
                    
                    # Add qualification results back to lead objects
                    for lead, qual in zip(leads, qualifications):
                        lead.qualification_result = qual
                    
                    # Filter to only qualified leads for Excel export
                    qualified_results = [
                        (lead, qual) 
                        for lead, qual in zip(leads, qualifications)
                        if qual.get('is_qualified', False)
                    ]
                    
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
                        print(f"📄 All leads Excel: {all_leads_excel}")
                        if args.filter_service:
                            print(f"🎯 Service Filter: {args.filter_service}")
                        print(f"✅ {qualified_count}/{total_leads} leads qualified ({qualification_rate:.1f}% qualification rate)")
                        print(f"📄 Qualified leads Excel: {excel_filename}")
                    else:
                        print("\n⚠️  No leads were qualified by the LLM")
                        if args.filter_service:
                            print(f"    (No leads found asking for {args.filter_service} services)")
                        print(f"📄 All scraped leads are still available in: {all_leads_excel}")
                        
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
