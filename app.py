"""Flask web application for Multi-Source Lead Scraping Engine."""

import asyncio
import json
import os
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename

from config.settings import settings
from models.lead import Lead
from scrapers.reddit_scraper import RedditScraper
from scrapers.discord_scraper import DiscordScraper
from scrapers.slack_scraper import SlackScraper
from scrapers.linkedin_public_scraper import LinkedInPublicScraper
from scrapers.linkedin_apify_scraper import LinkedInApifyScraper
from scrapers.linkedin_pw_scraper import LinkedInPlaywrightScraper
from scrapers.linkedin_sl_scraper import LinkedInSeleniumScraper
from storage.json_handler import append_leads
from storage.excel_handler import export_to_excel
from utils.llm_handler import qualify_leads_concurrent

# Import LinkedIn Streamlit scraper functions
import sys
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import random
import time


app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['UPLOAD_FOLDER'] = 'data'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure data directory exists
Path('data').mkdir(exist_ok=True)

# Global state for tracking scraping jobs
scraping_jobs = {}


def run_async_in_thread(coro):
    """Run async function in a separate thread with its own event loop."""
    def thread_target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()
    
    thread = threading.Thread(target=thread_target, daemon=True)
    thread.start()
    return thread


async def run_scraper(source: str, keywords: list[str], days_filter: int = 30, service_filter: str = None) -> list[Lead]:
    """Run a single scraper with timeout and error handling."""
    try:
        if source == 'reddit':
            if not settings.reddit.client_id or not settings.reddit.client_secret:
                print(f"⚠️ Reddit credentials not configured")
                return []
            
            # Apply service-based subreddit filtering
            subreddits = settings.reddit.subreddits
            if service_filter and service_filter in settings.reddit.SERVICE_SUBREDDITS:
                service_subreddits = settings.reddit.SERVICE_SUBREDDITS[service_filter]
                # Filter to only subreddits relevant for this service
                subreddits = [sub for sub in settings.reddit.subreddits if sub in service_subreddits]
                print(f"🎯 Reddit: Using {len(subreddits)} subreddits for service '{service_filter}'")
            
            scraper = RedditScraper(
                client_id=settings.reddit.client_id,
                client_secret=settings.reddit.client_secret,
                user_agent=settings.reddit.user_agent,
                keywords=keywords,
                subreddits=subreddits,
                rate_limit=settings.reddit.rate_limit,
                days_filter=days_filter,
                skip_keyword_filter=True  # Use soft filter for better recall
            )
            # Add 5-minute timeout per source
            return await asyncio.wait_for(scraper.scrape_with_rate_limit(), timeout=300)
        
        elif source == 'discord':
            if not settings.discord.bot_token:
                print(f"⚠️ Discord bot token not configured")
                return []
            scraper = DiscordScraper(
                bot_token=settings.discord.bot_token,
                keywords=keywords,
                channel_ids=settings.discord.channels,
                rate_limit=settings.discord.rate_limit
            )
            return await asyncio.wait_for(scraper.scrape_with_rate_limit(), timeout=300)
        
        elif source == 'slack':
            if not settings.slack.bot_token:
                print(f"⚠️ Slack bot token not configured")
                return []
            scraper = SlackScraper(
                bot_token=settings.slack.bot_token,
                keywords=keywords,
                channel_ids=settings.slack.channels,
                rate_limit=settings.slack.rate_limit
            )
            return await asyncio.wait_for(scraper.scrape_with_rate_limit(), timeout=300)
        
        elif source == 'linkedin_public':
            if settings.linkedin_public.enabled:
                scraper = LinkedInPublicScraper(
                    keywords=keywords[:3],
                    user_agents=[],
                    rate_limit=settings.linkedin_public.rate_limit
                )
                return await scraper.scrape_with_rate_limit()
            return []
        
        elif source == 'linkedin_apify':
            if settings.linkedin_apify.enabled:
                if not settings.linkedin_apify.apify_token:
                    print(f"⚠️ LinkedIn Apify token not configured")
                    return []
                scraper = LinkedInApifyScraper(
                    apify_token=settings.linkedin_apify.apify_token,
                    keywords=keywords,
                    max_posts_per_keyword=settings.linkedin_apify.max_posts_per_keyword,
                    rate_limit=settings.linkedin_apify.rate_limit,
                    actor_id=settings.linkedin_apify.actor_id,
                    linkedin_cookie=settings.linkedin_apify.linkedin_cookie,
                    proxy_config=settings.linkedin_apify.proxy_config,
                    max_total_leads=settings.scraping.max_total_leads,
                    days_filter=settings.linkedin_apify.days_filter
                )
                return await asyncio.wait_for(scraper.scrape_with_rate_limit(), timeout=300)
            return []
        
        elif source == 'linkedin_pw':
            if not settings.linkedin_apify.linkedin_cookie:
                print(f"⚠️ LinkedIn cookie not configured")
                return []
            scraper = LinkedInPlaywrightScraper(
                linkedin_cookie=settings.linkedin_apify.linkedin_cookie,
                keywords=keywords,
                rate_limit=10,
                headless=True
            )
            return await asyncio.wait_for(scraper.scrape_with_rate_limit(), timeout=300)
        
        elif source == 'linkedin_sl':
            if not settings.linkedin_apify.linkedin_cookie:
                print(f"⚠️ LinkedIn cookie not configured")
                return []
            scraper = LinkedInSeleniumScraper(
                linkedin_cookie=settings.linkedin_apify.linkedin_cookie,
                keywords=keywords,
                rate_limit=10,
                headless=True
            )
            return await asyncio.wait_for(scraper.scrape_with_rate_limit(), timeout=300)
        
        elif source == 'linkedin_selenium2':
            # LinkedIn Selenium2 scraper is handled separately in run_scraping_job
            # with its settings passed from the frontend
            print(f"ℹ️ LinkedIn Selenium2 scraper will be processed separately")
            return []
        
    except asyncio.TimeoutError:
        print(f"⏱️ {source}: Scraping timeout (5 minutes)")
        return []
    except Exception as e:
        print(f"❌ {source}: Scraping failed - {str(e)}")
        return []


@app.route('/')
def index():
    """Render main page."""
    return render_template('index.html')


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration."""
    return jsonify({
        'sources': {
            'reddit': bool(settings.reddit.client_id),
            'discord': bool(settings.discord.bot_token),
            'slack': bool(settings.slack.bot_token),
            'linkedin_public': settings.linkedin_public.enabled,
            'linkedin_apify': settings.linkedin_apify.enabled,
            'linkedin_pw': bool(settings.linkedin_apify.linkedin_cookie),
            'linkedin_sl': bool(settings.linkedin_apify.linkedin_cookie),
            'linkedin_selenium2': True  # Always available - automatic login mode
        },
        'llm': {
            'openai_configured': bool(settings.openai_api_key),
            'gemini_configured': bool(os.getenv('GEMINI_API_KEY')),
            'model': settings.llm_model,
            'min_confidence': settings.min_confidence_score
        },
        'service_presets': list(settings.scraping.KEYWORD_PRESETS.keys()),
        'default_max_leads': settings.scraping.max_total_leads,
        'competitors': settings.scraping.COMPETITORS if hasattr(settings.scraping, 'COMPETITORS') else []
    })


@app.route('/api/scrape', methods=['POST'])
def start_scrape():
    """Start a scraping job."""
    data = request.json
    
    # Validate input
    sources = data.get('sources', [])
    service_preset = data.get('service_preset', None)
    custom_keywords = data.get('custom_keywords', [])
    max_leads = data.get('max_leads', 200)
    qualify = data.get('qualify', False)
    filter_service = data.get('filter_service', None)
    min_confidence = data.get('min_confidence', 0.65)  # Minimum confidence score
    days_filter = data.get('days_filter', 30)  # Date filter for LinkedIn
    selenium2_settings = data.get('selenium2_settings', {})  # LinkedIn Selenium2 settings
    
    if not sources:
        return jsonify({'error': 'No sources selected'}), 400
    
    # Determine keywords
    if service_preset and service_preset in settings.scraping.KEYWORD_PRESETS:
        keywords = settings.scraping.KEYWORD_PRESETS[service_preset]
    elif custom_keywords:
        keywords = custom_keywords
    else:
        keywords = settings.scraping.keywords
    
    # Create job ID
    job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    # Store job info
    scraping_jobs[job_id] = {
        'status': 'running',
        'sources': sources,
        'keywords': keywords,
        'max_leads': max_leads,
        'qualify': qualify,
        'filter_service': filter_service,
        'min_confidence': min_confidence,
        'service_preset': service_preset,  # Track which preset was used
        'days_filter': days_filter,
        'selenium2_settings': selenium2_settings,  # LinkedIn Selenium2 settings
        'started_at': datetime.now().isoformat(),
        'progress': 0,
        'leads_found': 0,
        'qualified_count': 0,
        'stop_requested': False  # Flag for early stopping
    }
    
    # Run scraping in background
    run_async_in_thread(run_scraping_job(job_id, sources, keywords, max_leads, qualify, filter_service, min_confidence, days_filter, service_preset, selenium2_settings))
    
    return jsonify({
        'job_id': job_id,
        'message': 'Scraping job started',
        'status': 'running'
    })


def search_and_scroll_linkedin(driver, keyword, max_scroll_attempts=10, stop_check=None):
    """Search for keyword and scroll through LinkedIn results."""
    all_posts = []
    search_url = f"https://www.linkedin.com/search/results/content/?keywords={keyword}&origin=GLOBAL_SEARCH_HEADER"
    driver.get(search_url)
    
    scroll_attempts = 0
    while scroll_attempts < max_scroll_attempts:
        # Check if stop was requested
        if stop_check and stop_check():
            print(f"⏹️ Stop requested. Collected {len(all_posts)} posts so far for '{keyword}'")
            break
        print(f"Scrolling attempt {scroll_attempts + 1}/{max_scroll_attempts}...")
        
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(random.uniform(4, 6))
        
        try:
            show_more_button = driver.find_element(By.XPATH,
                                                   "//button[contains(@class, 'scaffold-finite-scroll__load-button')]")
            if show_more_button.is_displayed():
                print("Clicking 'Show more results' button.")
                show_more_button.click()
                time.sleep(random.uniform(2, 4) + 5)
            else:
                print("Reached the end of results.")
                break
        except NoSuchElementException:
            print("Reached the end of results.")
            break
        except StaleElementReferenceException:
            print("Encountered a stale element. Retrying...")
        
        # Extract posts from current page
        page_posts = extract_linkedin_posts(driver.page_source)
        all_posts.extend(page_posts)
        
        scroll_attempts += 1
    
    return all_posts


def extract_linkedin_posts(html):
    """Extract post information from LinkedIn HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    posts = []
    post_elements = soup.find_all('div', class_='feed-shared-update-v2')
    
    print(f"Found {len(post_elements)} post elements on this page")
    
    for post in post_elements:
        try:
            profile_link = post.find('a', class_='app-aware-link update-components-actor__meta-link')
            if not profile_link:
                continue
            
            profile_url = profile_link.get('href', '')
            profile_name = profile_link.find('span', class_='update-components-actor__name')
            profile_name = profile_name.text.strip() if profile_name else "Name not found"
            
            profile_title = profile_link.find('span', class_='update-components-actor__description')
            profile_title = profile_title.text.strip() if profile_title else "Title not found"
            
            connection_degree = profile_link.find('span', class_='update-components-actor__supplementary-actor-info')
            connection_degree = connection_degree.text.strip() if connection_degree else "Connection degree not found"
            
            timestamp = post.find('span', class_='update-components-actor__sub-description')
            timestamp = timestamp.text.strip() if timestamp else "Timestamp not found"
            
            content_section = post.find('div', class_='feed-shared-update-v2__description-wrapper')
            content = content_section.text.strip() if content_section else "No content"
            
            hashtags = [tag.text for tag in
                        post.find_all('a', class_='feed-shared-text-view__mention')] if content_section else []
            
            posts.append({
                'profile_name': profile_name,
                'profile_title': profile_title,
                'profile_url': profile_url,
                'connection_degree': connection_degree,
                'timestamp': timestamp,
                'content': content,
                'hashtags': ', '.join(hashtags)
            })
        
        except AttributeError as e:
            print(f"Error extracting post data: {e}")
    
    return posts


def login_to_linkedin_auto(driver, username, password):
    """Login to LinkedIn using username and password."""
    try:
        print("Navigating to LinkedIn login page...")
        driver.get("https://www.linkedin.com/login")
        time.sleep(3)
        
        print("Finding login fields...")
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "username")))
        
        username_field = driver.find_element(By.ID, "username")
        password_field = driver.find_element(By.ID, "password")
        
        print("Entering credentials...")
        username_field.clear()
        time.sleep(0.5)
        username_field.send_keys(username)
        time.sleep(1)
        
        password_field.clear()
        time.sleep(0.5)
        password_field.send_keys(password)
        time.sleep(1)
        
        print("Submitting login form...")
        password_field.send_keys(Keys.RETURN)
        time.sleep(5)
        
        # Check if login was successful
        current_url = driver.current_url
        print(f"Current URL after login: {current_url}")
        
        if "checkpoint" in current_url or "challenge" in current_url:
            print("❌ LinkedIn requires verification")
            return False
        
        if "login" in current_url and "feed" not in current_url:
            print("❌ Login failed")
            return False
        
        try:
            WebDriverWait(driver, 15).until(
                lambda d: "feed" in d.current_url or "mynetwork" in d.current_url or "linkedin.com/in/" in d.current_url
            )
            print("✅ Successfully logged in!")
            return True
        except TimeoutException:
            print(f"⚠️ Login may have succeeded but couldn't confirm")
            return "linkedin.com" in current_url and "login" not in current_url
    
    except Exception as e:
        print(f"❌ Login failed with error: {str(e)}")
        return False


async def run_linkedin_selenium2_scraper(keywords: list[str], settings: dict, job_id: str) -> list[Lead]:
    """Run LinkedIn Selenium2 scraper asynchronously in Flask background job."""
    try:
        print("\n=== Starting LinkedIn Selenium2 scraping ===")
        print(f"📋 Settings received: {settings}")
        scroll_attempts = settings.get('scroll_attempts', 10)
        username = settings.get('username', '')
        password = settings.get('password', '')
        headless = settings.get('headless', False)  # Default to visible browser
        manual_login = settings.get('manual_login', True)  # Default to manual login
        
        print(f"🔧 Configuration: headless={headless}, manual_login={manual_login}")
        
        # Helper function to check if stop was requested
        def should_stop():
            return scraping_jobs.get(job_id, {}).get('stop_requested', False)
        
        # Setup Chrome options
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")  # Run headless (no visible browser)
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-notifications")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False
        })
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        print("✅ Chrome browser initialized")
        
        # Login handling
        if manual_login:
            print("👤 Manual login mode - Opening browser for user to login...")
            driver.get("https://www.linkedin.com/login")
            print("⏳ Waiting for user to login manually...")
            print("   Please login and navigate to your feed, then scraping will start automatically")
            
            # Wait up to 5 minutes for user to login (check for feed URL)
            wait_time = 0
            max_wait = 300  # 5 minutes
            while wait_time < max_wait:
                time.sleep(5)
                wait_time += 5
                current_url = driver.current_url
                
                # Check if user has logged in (reached feed or profile)
                if "feed" in current_url or "mynetwork" in current_url or "/in/" in current_url:
                    print("✅ Manual login detected! Starting scraping...")
                    break
                    
                if wait_time % 30 == 0:  # Print status every 30 seconds
                    print(f"   Still waiting for login... ({wait_time}/{max_wait}s)")
            
            if wait_time >= max_wait:
                print("❌ Timeout waiting for manual login")
                driver.quit()
                return []
        else:
            # Automatic login
            if not username or not password:
                print("❌ Username or password not provided for LinkedIn Selenium2")
                driver.quit()
                return []
            
            print("🔐 Attempting automatic login to LinkedIn...")
            if not login_to_linkedin_auto(driver, username, password):
                print("❌ LinkedIn login failed")
                driver.quit()
                return []
        
        # Scrape for each keyword
        all_posts = []
        for keyword in keywords:
            # Check if stop was requested before starting new keyword
            if should_stop():
                print(f"⏹️ Stop requested. Stopping after {len(keywords.index(keyword))} keyword(s)")
                break
                
            print(f"Searching for keyword: {keyword}")
            posts = search_and_scroll_linkedin(driver, keyword, scroll_attempts, should_stop)
            all_posts.extend(posts)
            
            # Check again before waiting
            if should_stop():
                print(f"⏹️ Stop requested. Skipping remaining keywords.")
                break
                
            time.sleep(random.uniform(5, 10))
        
        # Remove duplicates
        seen = set()
        unique_posts = []
        for post in all_posts:
            post_key = (post['profile_name'], post['profile_url'], post['content'][:100])
            if post_key not in seen:
                seen.add(post_key)
                unique_posts.append(post)
        
        was_stopped = should_stop()
        print(f"✓ LinkedIn Selenium2: Found {len(unique_posts)} unique posts{' (stopped early)' if was_stopped else ''}")
        
        # Convert to Lead objects
        leads = []
        for post in unique_posts:
            lead = Lead(
                source="linkedin_selenium2",
                content=post['content'],
                author=post['profile_name'],
                author_profile=post['profile_url'],
                author_info=post['profile_title'],
                timestamp=post['timestamp'],
                url=post['profile_url'],
                additional_data={
                    'connection_degree': post['connection_degree'],
                    'hashtags': post['hashtags']
                }
            )
            leads.append(lead)
        
        driver.quit()
        return leads
    
    except Exception as e:
        print(f"✗ LinkedIn Selenium2 scraping failed: {e}")
        import traceback
        traceback.print_exc()
        return []


async def run_scraping_job(job_id: str, sources: list, keywords: list, max_leads: int, qualify: bool, filter_service: str, min_confidence: float = 0.65, days_filter: int = 30, service_preset: str = None, selenium2_settings: dict = None):
    """Run scraping job in background."""
    try:
        # Update max leads, min confidence, and days filter (universal for all sources)
        settings.scraping.max_total_leads = max_leads
        settings.min_confidence_score = min_confidence  # Set confidence threshold
        settings.scraping.days_filter = days_filter  # Universal days filter
        settings.linkedin_apify.days_filter = days_filter  # LinkedIn-specific (kept for backward compat)
        
        # Handle LinkedIn Selenium2 separately if selected
        linkedin_selenium2_leads = []
        if 'linkedin_selenium2' in sources:
            sources.remove('linkedin_selenium2')  # Remove from concurrent batch
            print("🔧 Running LinkedIn Selenium2 scraper (opens browser automatically)...")
            linkedin_selenium2_leads = await run_linkedin_selenium2_scraper(
                keywords, 
                selenium2_settings or {},
                job_id
            )
        
        # Run other scrapers concurrently (pass days_filter and service to each scraper)
        tasks = [run_scraper(source, keywords, days_filter, service_preset) for source in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Flatten results
        all_leads = linkedin_selenium2_leads.copy()  # Start with Selenium2 leads
        for result in results:
            if isinstance(result, list):
                all_leads.extend(result)
        
        scraping_jobs[job_id]['leads_found'] = len(all_leads)
        scraping_jobs[job_id]['progress'] = 50
        
        # Save leads
        output_file = f"data/leads_{job_id}.json"
        append_leads(all_leads, output_file)
        scraping_jobs[job_id]['output_file'] = output_file
        
        # ALWAYS export all leads to Excel (even if empty)
        from storage.excel_handler import export_all_leads_to_excel
        all_leads_excel = f"data/all_leads_{job_id}.xlsx"
        export_all_leads_to_excel(all_leads, all_leads_excel)
        scraping_jobs[job_id]['all_leads_excel'] = all_leads_excel
        
        # Qualify if requested
        if qualify and all_leads:
            scraping_jobs[job_id]['progress'] = 60
            scraping_jobs[job_id]['status'] = 'qualifying'
            
            qualifications = await qualify_leads_concurrent(
                all_leads,
                max_concurrent=settings.max_concurrent_llm_requests,
                target_service=filter_service
            )
            
            # Add qualification results
            for lead, qual in zip(all_leads, qualifications):
                lead.qualification_result = qual
            
            # Filter qualified leads by confidence threshold
            qualified_leads = [
                lead for lead, qual in zip(all_leads, qualifications)
                if qual.get('is_qualified', False) and qual.get('confidence_score', 0) >= min_confidence
            ]
            
            scraping_jobs[job_id]['qualified_count'] = len(qualified_leads)
            
            # Export to Excel
            if qualified_leads:
                excel_file = f"data/qualified_leads_{job_id}.xlsx"
                export_to_excel(
                    qualified_leads,
                    [qual for qual in qualifications if qual.get('is_qualified', False)],
                    excel_file
                )
                scraping_jobs[job_id]['excel_file'] = excel_file
            
            # Update JSON with qualifications
            append_leads(all_leads, output_file)
        
        scraping_jobs[job_id]['status'] = 'completed'
        scraping_jobs[job_id]['progress'] = 100
        scraping_jobs[job_id]['completed_at'] = datetime.now().isoformat()
        
    except Exception as e:
        scraping_jobs[job_id]['status'] = 'failed'
        scraping_jobs[job_id]['error'] = str(e)
        print(f"Job {job_id} failed: {e}")


@app.route('/api/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Get status of a scraping job."""
    if job_id not in scraping_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify(scraping_jobs[job_id])


@app.route('/api/jobs/<job_id>/stop', methods=['POST'])
def stop_job(job_id):
    """Request to stop a scraping job early."""
    if job_id not in scraping_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = scraping_jobs[job_id]
    
    if job['status'] not in ['running', 'qualifying']:
        return jsonify({'error': 'Job is not running'}), 400
    
    job['stop_requested'] = True
    print(f"⏹️ Stop requested for job {job_id}")
    
    return jsonify({
        'message': 'Stop request received. Job will finish current operation and process collected leads.',
        'status': 'stopping'
    })


@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """List all scraping jobs."""
    return jsonify({
        'jobs': [
            {'job_id': job_id, **job_info}
            for job_id, job_info in scraping_jobs.items()
        ]
    })


@app.route('/api/download/<job_id>/<file_type>', methods=['GET'])
def download_file(job_id, file_type):
    """Download result file."""
    if job_id not in scraping_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = scraping_jobs[job_id]
    
    if file_type == 'json' and 'output_file' in job:
        return send_file(job['output_file'], as_attachment=True)
    elif file_type == 'excel' and 'excel_file' in job:
        return send_file(job['excel_file'], as_attachment=True)
    else:
        return jsonify({'error': 'File not found'}), 404


@app.route('/api/leads/<job_id>', methods=['GET'])
def get_leads(job_id):
    """Get leads from a job."""
    if job_id not in scraping_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = scraping_jobs[job_id]
    if 'output_file' not in job:
        return jsonify({'error': 'No leads file found'}), 404
    
    try:
        with open(job['output_file'], 'r', encoding='utf-8') as f:
            leads = json.load(f)
        
        # Pagination
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        
        start = (page - 1) * per_page
        end = start + per_page
        
        return jsonify({
            'leads': leads[start:end],
            'total': len(leads),
            'page': page,
            'per_page': per_page,
            'pages': (len(leads) + per_page - 1) // per_page
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get overall statistics."""
    total_jobs = len(scraping_jobs)
    completed_jobs = sum(1 for j in scraping_jobs.values() if j['status'] == 'completed')
    total_leads = sum(j.get('leads_found', 0) for j in scraping_jobs.values())
    total_qualified = sum(j.get('qualified_count', 0) for j in scraping_jobs.values())
    
    return jsonify({
        'total_jobs': total_jobs,
        'completed_jobs': completed_jobs,
        'running_jobs': sum(1 for j in scraping_jobs.values() if j['status'] == 'running'),
        'failed_jobs': sum(1 for j in scraping_jobs.values() if j['status'] == 'failed'),
        'total_leads': total_leads,
        'total_qualified': total_qualified,
        'qualification_rate': f"{(total_qualified / total_leads * 100):.1f}%" if total_leads > 0 else "0%"
    })


if __name__ == '__main__':
    # Run Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)
