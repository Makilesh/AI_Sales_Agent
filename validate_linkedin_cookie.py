"""
LinkedIn Cookie Validator
Tests if your li_at cookie is valid by attempting to access LinkedIn feed.
Run this BEFORE using the full scraper to verify authentication.
"""

import asyncio
from playwright.async_api import async_playwright
from decouple import config

async def validate_linkedin_cookie():
    """Test if LinkedIn cookie is valid."""
    
    # Load cookie from .env
    cookie = config("LINKEDIN_COOKIE", default="")
    
    if not cookie:
        print("❌ ERROR: No LINKEDIN_COOKIE found in .env file")
        print("\nPlease add your LinkedIn li_at cookie to .env:")
        print("LINKEDIN_COOKIE=AQEDAWDa7CcE...")
        return False
    
    print("=" * 70)
    print("LinkedIn Cookie Validator")
    print("=" * 70)
    print(f"\n📋 Cookie loaded: {cookie[:20]}...{cookie[-20:]}")
    print(f"   Length: {len(cookie)} characters")
    
    if len(cookie) < 100:
        print("\n⚠️  WARNING: Cookie seems too short (should be ~180 characters)")
        print("   Make sure you copied the entire li_at cookie value")
    
    print("\n🚀 Launching browser to test authentication...")
    
    playwright = await async_playwright().start()
    
    try:
        # Launch browser in visible mode
        browser = await playwright.chromium.launch(
            headless=False,  # Visible so you can see what happens
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
            ]
        )
        
        # Create context with cookie
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080},
        )
        
        # Add cookie
        await context.add_cookies([{
            'name': 'li_at',
            'value': cookie,
            'domain': '.linkedin.com',
            'path': '/',
            'secure': True,
            'httpOnly': True,
            'sameSite': 'None'
        }])
        
        page = await context.new_page()
        
        # Try to access LinkedIn feed
        print("🔐 Navigating to LinkedIn feed...")
        try:
            # Use domcontentloaded instead of networkidle (more forgiving)
            await page.goto('https://www.linkedin.com/feed/', wait_until='domcontentloaded', timeout=30000)
            print("   ✓ Page loaded, waiting for content...")
            await asyncio.sleep(5)  # Give it time to load
        except Exception as nav_error:
            print(f"   ⚠️ Navigation warning: {nav_error}")
            print("   Checking current state anyway...")
            await asyncio.sleep(3)
        
        current_url = page.url
        print(f"   Current URL: {current_url}")
        
        # Check authentication status
        if 'authwall' in current_url or 'login' in current_url or 'checkpoint' in current_url:
            print("\n❌ AUTHENTICATION FAILED")
            print(f"   Redirected to: {current_url}")
            print("\n🔧 Your cookie is INVALID or EXPIRED. You need to:")
            print("   1. Log into LinkedIn in a normal browser")
            print("   2. Open DevTools (F12) → Application → Cookies")
            print("   3. Copy the NEW li_at cookie value")
            print("   4. Update LINKEDIN_COOKIE in .env file")
            
            input("\n👀 Browser will stay open so you can see the error. Press Enter to close...")
            success = False
            
        else:
            # Look for profile elements - try multiple selectors
            try:
                print("🔍 Checking for profile elements...")
                
                # Try multiple ways to detect logged-in state
                profile_found = False
                
                # Method 1: Look for "Me" dropdown
                try:
                    await page.wait_for_selector('button:has-text("Me")', timeout=5000)
                    profile_found = True
                except:
                    pass
                
                # Method 2: Look for profile image/name
                if not profile_found:
                    try:
                        await page.wait_for_selector('[data-control-name="identity_profile_photo"]', timeout=5000)
                        profile_found = True
                    except:
                        pass
                
                # Method 3: Check for common logged-in elements
                if not profile_found:
                    try:
                        await page.wait_for_selector('.global-nav__me', timeout=5000)
                        profile_found = True
                    except:
                        pass
                
                if profile_found:
                    print("\n✅ AUTHENTICATION SUCCESSFUL!")
                    print("   You are logged into LinkedIn")
                    print("   Your li_at cookie is VALID")
                    print("\n🎉 You can now use the Playwright scraper:")
                    print("   python main.py --sources linkedin_pw --service rwa_linkedin --max-total-leads 10")
                    success = True
                else:
                    print("\n⚠️  Could not auto-detect profile")
                    print(f"   Current URL: {current_url}")
                    print("\n   👀 CHECK THE BROWSER: Do you see your profile/name in top-right?")
                    response = input("   Type 'yes' if you see your profile, or 'no' if not logged in: ").strip().lower()
                    
                    if response in ['yes', 'y']:
                        print("\n✅ Great! Your cookie IS VALID (manual confirmation)")
                        print("   You can use the Playwright scraper")
                        success = True
                    else:
                        print("\n❌ Cookie appears invalid - update it")
                        success = False
                
                input("\n👀 Press Enter to close browser...")
                
            except Exception as e:
                print(f"\n⚠️  Detection error: {e}")
                print(f"   Current URL: {current_url}")
                
                input("\n👀 Check if you see your profile in top-right corner. Press Enter to close...")
                success = False
        
        await browser.close()
        await playwright.stop()
        
        return success
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("\nTroubleshooting:")
        print("- Make sure Playwright is installed: pip install playwright")
        print("- Install browsers: playwright install chromium")
        print("- Check your internet connection")
        
        try:
            await browser.close()
            await playwright.stop()
        except:
            pass
        
        return False


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("IMPORTANT: This will open a visible browser window")
    print("You'll be able to see if authentication succeeds or fails")
    print("=" * 70)
    
    result = asyncio.run(validate_linkedin_cookie())
    
    if result:
        print("\n✅ Cookie validation PASSED - Ready to scrape!")
    else:
        print("\n❌ Cookie validation FAILED - Update your cookie first")
        print("📚 See LINKEDIN_PLAYWRIGHT_TROUBLESHOOTING.md for detailed help")
