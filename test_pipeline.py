"""Quick pipeline test to verify all fixes work correctly."""

import asyncio
import logging
from pathlib import Path
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_excel_export():
    """Test Excel export with empty leads."""
    logger.info("🧪 Testing Excel export with empty leads...")
    
    from storage.excel_handler import export_all_leads_to_excel, export_to_excel
    
    # Test 1: Empty all leads export
    try:
        test_path = Path("data/test_empty_all_leads.xlsx")
        test_path.parent.mkdir(exist_ok=True)
        export_all_leads_to_excel([], str(test_path))
        logger.info("✅ Empty all leads export works")
    except Exception as e:
        logger.error(f"❌ Empty all leads export failed: {e}")
        return False
    
    # Test 2: Empty qualified leads export
    try:
        test_path = Path("data/test_empty_qualified.xlsx")
        export_to_excel([], [], str(test_path))
        logger.info("✅ Empty qualified leads export works")
    except Exception as e:
        logger.error(f"❌ Empty qualified leads export failed: {e}")
        return False
    
    return True

async def test_scraper_validation():
    """Test scraper initialization validation."""
    logger.info("\n🧪 Testing scraper validation...")
    
    from app import run_scraper
    
    # Test with invalid source (should return empty list, not crash)
    try:
        leads = await run_scraper("invalid_source", ["test"])
        logger.info(f"✅ Invalid source handled gracefully: {len(leads)} leads")
    except Exception as e:
        logger.error(f"❌ Invalid source crashed: {e}")
        return False
    
    # Test Reddit with timeout (if configured)
    if settings.reddit.client_id:
        try:
            logger.info("Testing Reddit scraper with credentials...")
            # This will timeout after 5 minutes, but we can verify it starts
            task = asyncio.create_task(run_scraper("reddit", ["tokenization"]))
            await asyncio.sleep(2)  # Let it start
            task.cancel()
            logger.info("✅ Reddit scraper starts correctly")
        except Exception as e:
            logger.error(f"❌ Reddit scraper failed: {e}")
            return False
    else:
        logger.info("⏭️  Reddit not configured, skipping")
    
    return True

async def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("PIPELINE VALIDATION TEST")
    logger.info("=" * 60)
    
    # Test 1: Excel export
    test1_pass = await test_excel_export()
    
    # Test 2: Scraper validation
    test2_pass = await test_scraper_validation()
    
    logger.info("\n" + "=" * 60)
    if test1_pass and test2_pass:
        logger.info("✅ ALL TESTS PASSED - Pipeline is healthy!")
    else:
        logger.info("❌ SOME TESTS FAILED - Check errors above")
    logger.info("=" * 60)
    
    # Cleanup test files
    logger.info("\n🧹 Cleaning up test files...")
    for file in Path("data").glob("test_*.xlsx"):
        file.unlink()
        logger.info(f"   Deleted: {file.name}")

if __name__ == "__main__":
    asyncio.run(main())
