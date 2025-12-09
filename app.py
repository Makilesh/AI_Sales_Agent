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
from storage.json_handler import append_leads
from storage.excel_handler import export_to_excel
from utils.llm_handler import qualify_leads_concurrent


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


async def run_scraper(source: str, keywords: list[str]) -> list[Lead]:
    """Run a single scraper."""
    try:
        if source == 'reddit':
            scraper = RedditScraper(
                client_id=settings.reddit.client_id,
                client_secret=settings.reddit.client_secret,
                user_agent=settings.reddit.user_agent,
                keywords=keywords,
                subreddits=settings.reddit.subreddits,
                rate_limit=settings.reddit.rate_limit
            )
            return await scraper.scrape_with_rate_limit()
        
        elif source == 'discord':
            scraper = DiscordScraper(
                bot_token=settings.discord.bot_token,
                keywords=keywords,
                channel_ids=settings.discord.channels,
                rate_limit=settings.discord.rate_limit
            )
            return await scraper.scrape_with_rate_limit()
        
        elif source == 'slack':
            scraper = SlackScraper(
                bot_token=settings.slack.bot_token,
                keywords=keywords,
                channel_ids=settings.slack.channels,
                rate_limit=settings.slack.rate_limit
            )
            return await scraper.scrape_with_rate_limit()
        
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
                scraper = LinkedInApifyScraper(
                    apify_token=settings.linkedin_apify.apify_token,
                    keywords=keywords,
                    max_posts_per_keyword=settings.linkedin_apify.max_posts_per_keyword,
                    rate_limit=settings.linkedin_apify.rate_limit,
                    actor_id=settings.linkedin_apify.actor_id,
                    linkedin_cookie=settings.linkedin_apify.linkedin_cookie,
                    proxy_config=settings.linkedin_apify.proxy_config,
                    max_total_leads=settings.scraping.max_total_leads
                )
                return await scraper.scrape_with_rate_limit()
            return []
        
    except Exception as e:
        print(f"Error scraping {source}: {e}")
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
            'linkedin_apify': settings.linkedin_apify.enabled
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
        'started_at': datetime.now().isoformat(),
        'progress': 0,
        'leads_found': 0,
        'qualified_count': 0
    }
    
    # Run scraping in background
    run_async_in_thread(run_scraping_job(job_id, sources, keywords, max_leads, qualify, filter_service))
    
    return jsonify({
        'job_id': job_id,
        'message': 'Scraping job started',
        'status': 'running'
    })


async def run_scraping_job(job_id: str, sources: list, keywords: list, max_leads: int, qualify: bool, filter_service: str):
    """Run scraping job in background."""
    try:
        # Update max leads
        settings.scraping.max_total_leads = max_leads
        
        # Run scrapers concurrently
        tasks = [run_scraper(source, keywords) for source in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Flatten results
        all_leads = []
        for result in results:
            if isinstance(result, list):
                all_leads.extend(result)
        
        scraping_jobs[job_id]['leads_found'] = len(all_leads)
        scraping_jobs[job_id]['progress'] = 50
        
        # Save leads
        output_file = f"data/leads_{job_id}.json"
        append_leads(all_leads, output_file)
        scraping_jobs[job_id]['output_file'] = output_file
        
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
            
            # Filter qualified
            qualified_leads = [
                lead for lead, qual in zip(all_leads, qualifications)
                if qual.get('is_qualified', False)
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
