# Changelog

All notable changes to the AI Sales Agent project will be documented in this file.

## [1.1.0] - 2024-12-09

### Added
- **Universal Excel Export**: ALL scraping jobs now generate Excel exports automatically, regardless of AI qualification status
- New export function `export_all_leads_to_excel()` in `storage/excel_handler.py`
- Two types of Excel downloads:
  - **Excel (All)**: Contains all scraped leads sorted by engagement score
  - **Excel (Qualified)**: Contains only AI-qualified leads sorted by confidence score (when qualification is enabled)
- Updated web frontend with two separate Excel download buttons
- Enhanced API endpoint `/api/download/<job_id>/excel_all` for all-leads Excel download
- CLI now exports both Excel files automatically
- Better cost optimization for users who want Excel format without LLM costs

### Changed
- Web UI now shows tooltips on Excel buttons to clarify content differences
- Job tracking in `app.py` now includes `all_leads_excel` field
- Main CLI prints paths to both Excel files in final summary

### Fixed
- LinkedIn Apify users can now get Excel exports without enabling AI qualification
- No more "Excel only available with qualification" limitation

### Benefits
- **Cost Savings**: Scrape to Excel without paying for LLM qualification ($0.01/lead saved)
- **Flexibility**: Choose between raw data (All) or qualified data (Qualified)
- **CRM Integration**: Import raw Excel data directly into your CRM
- **Manual Review**: Review all leads in Excel before deciding which to qualify

---

## [1.0.0] - 2024-12-09

### Added
- Multi-source lead scraping (Reddit, Discord, Slack, LinkedIn Public, LinkedIn Apify)
- Dual LLM system (OpenAI GPT-4-turbo + Gemini 2.5 Flash fallback)
- 3-stage pre-validation filter (saves 94.6% on LLM costs)
- Competitor frustration detection (16 India-based Web3/blockchain competitors)
- Flask web application with responsive UI
- REST API with 8 endpoints
- Real-time job tracking and progress monitoring
- Service-specific keyword presets (22 presets)
- JSON and Excel export functionality
- CLI interface with argparse
- Configuration management via `.env` file
- Rate limiting for all scrapers
- Concurrent LLM qualification
- Engagement score calculation
- Lead deduplication by URL

### Features
- **Web Frontend**: Modern purple gradient UI with control panel
- **Real-time Updates**: Progress bars and status indicators
- **Statistics Dashboard**: Track total jobs, leads, qualification rate
- **Download Options**: JSON and Excel formats
- **Service Filtering**: Filter qualified leads by service type
- **Custom Keywords**: User-defined keyword search
- **Source Selection**: Choose specific platforms to scrape
- **Async/Sync Bridge**: Thread-based solution for Flask + AsyncIO compatibility

---

## Release Notes

### v1.1.0 Highlights

**The Excel Export Update** 🎉

We heard your feedback! LinkedIn Apify users and others wanted Excel format without the AI qualification requirement. Now:

1. **Every scraping job generates Excel** - No exceptions!
2. **Two Excel files**:
   - `all_leads_XXXXX.xlsx` - Everything you scraped (raw data)
   - `qualified_leads_XXXXX.xlsx` - Only the AI-approved leads (if qualification was on)
3. **Save money**: Scrape 500 LinkedIn leads → Get Excel → Review manually → Only qualify the promising ones
4. **Better workflow**: Import raw Excel into your CRM, then use AI qualification selectively

**Cost Example**:
- Old way: Scrape 500 leads → Must qualify all to get Excel → $5 LLM cost
- New way: Scrape 500 leads → Get Excel for free → Manually pick 50 best → Qualify those → $0.50 LLM cost

**Migration Notes**:
- No breaking changes! Old qualified Excel still works
- Web UI automatically shows both buttons when available
- CLI updated to generate both files by default
- API endpoint remains backward compatible (`/excel` still works)

---

## Coming Soon

### v1.2.0 (Planned)
- Lead detail modal viewer in web UI
- Job persistence (database integration)
- User authentication and authorization
- Export to CSV format
- Bulk operations on leads
- Search and filter in web UI
- Lead tagging system
- Notes and follow-up tracking

### v1.3.0 (Planned)
- Email integration for follow-ups
- Slack/Discord notifications
- Webhook support
- API rate monitoring dashboard
- Cost tracking per job
- Lead scoring customization
- Integration with CRM platforms (HubSpot, Salesforce)

---

## Support

For issues, questions, or feature requests:
- Contact: Makilesh (Shamla Tech)
- Repository: https://github.com/Makilesh/ai_sales_agent

---

**Last Updated**: December 9, 2024
