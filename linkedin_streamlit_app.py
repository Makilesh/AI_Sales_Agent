"""
LinkedIn Lead Scraper - Streamlit App
A web-based interface for scraping and analyzing LinkedIn leads.
"""

import os
import streamlit as st
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
import pandas as pd
from datetime import datetime
import time
from openai import OpenAI
import random
from dotenv import load_dotenv
import gc
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# Load environment variables
load_dotenv()

# Configure the OpenAI API
# Use environment variable for security
openai_api_key = os.getenv('OPENAI_API_KEY', '')
if openai_api_key:
    client = OpenAI(api_key=openai_api_key)
else:
    st.error("OPENAI_API_KEY not found in .env file")
    st.stop()

# Set page config to wide mode
st.set_page_config(layout="wide", page_title="LinkedIn Lead Scraper")

# Custom CSS to ensure full width
st.markdown("""
<style>
    .reportview-container .main .block-container {
        max-width: 1000px;
        padding-top: 1rem;
        padding-right: 1rem;
        padding-left: 1rem;
        padding-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)


def login_to_linkedin(driver, username, password):
    """Login to LinkedIn using username and password."""
    try:
        st.info("Navigating to LinkedIn login page...")
        driver.get("https://www.linkedin.com/login")
        time.sleep(3)
        
        st.info("Finding login fields...")
        WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "username")))
        
        username_field = driver.find_element(By.ID, "username")
        password_field = driver.find_element(By.ID, "password")
        
        st.info("Entering credentials...")
        username_field.clear()
        time.sleep(0.5)
        username_field.send_keys(username)
        time.sleep(1)
        
        password_field.clear()
        time.sleep(0.5)
        password_field.send_keys(password)
        time.sleep(1)
        
        st.info("Submitting login form...")
        password_field.send_keys(Keys.RETURN)
        
        # Wait longer for page to load
        time.sleep(5)
        
        # Check current URL
        current_url = driver.current_url
        st.info(f"Current URL after login: {current_url}")
        
        # Check for various post-login scenarios
        if "checkpoint" in current_url or "challenge" in current_url:
            st.error("❌ LinkedIn requires verification. This account may need to verify login from a browser first.")
            st.error("Please login manually in a browser, complete any verification, then try again.")
            return False
        
        if "login" in current_url and "feed" not in current_url:
            st.error("❌ Login failed. Possible reasons:")
            st.error("- Incorrect credentials")
            st.error("- Account locked or suspended")
            st.error("- LinkedIn detected automation")
            return False
        
        # Try to wait for feed page
        try:
            WebDriverWait(driver, 15).until(
                lambda d: "feed" in d.current_url or "mynetwork" in d.current_url or "linkedin.com/in/" in d.current_url
            )
            st.success("✅ Successfully logged in!")
            return True
        except TimeoutException:
            st.warning(f"⚠️ Login may have succeeded but couldn't confirm. Current URL: {current_url}")
            # Try to continue anyway
            if "linkedin.com" in current_url and "login" not in current_url:
                return True
            return False
            
    except TimeoutException as e:
        st.error(f"❌ Timeout during login: Page elements took too long to load")
        st.error(f"Details: {str(e)}")
        return False
    except NoSuchElementException as e:
        st.error(f"❌ Could not find login elements on page")
        st.error(f"Details: {str(e)}")
        return False
    except Exception as e:
        st.error(f"❌ Login failed with error: {str(e)}")
        st.error(f"Error type: {type(e).__name__}")
        import traceback
        st.error(f"Traceback: {traceback.format_exc()}")
        return False


def search_and_scroll(driver, keyword, max_scroll_attempts=50):
    """Search for keyword and scroll through results."""
    all_posts = []
    search_url = f"https://www.linkedin.com/search/results/content/?keywords={keyword}&origin=GLOBAL_SEARCH_HEADER"
    driver.get(search_url)

    scroll_attempts = 0

    with st.empty():
        while scroll_attempts < max_scroll_attempts:
            st.info(f"Scrolling attempt {scroll_attempts + 1}...")

            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(4, 6))

            try:
                show_more_button = driver.find_element(By.XPATH,
                                                       "//button[contains(@class, 'scaffold-finite-scroll__load-button')]")
                if show_more_button.is_displayed():
                    st.info("Clicking 'Show more results' button.")
                    show_more_button.click()
                    time.sleep(random.uniform(2, 4) + 5)
                else:
                    st.success("Reached the end of results. Stopping scroll.")
                    break
            except NoSuchElementException:
                st.success("Reached the end of results. Stopping scroll.")
                break
            except StaleElementReferenceException:
                st.info("Encountered a stale element. Retrying...")

            page_posts = extract_post_info(driver.page_source)
            all_posts.extend(page_posts)

            scroll_attempts += 1

    return all_posts


def extract_post_info(html):
    """Extract post information from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    posts = []
    post_elements = soup.find_all('div', class_='feed-shared-update-v2')

    st.info(f"Found {len(post_elements)} post elements on this page")

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
                'Profile Name': profile_name,
                'Profile Title': profile_title,
                'Profile URL': profile_url,
                'Connection Degree': connection_degree,
                'Timestamp': timestamp,
                'Content': content,
                'Hashtags': ', '.join(hashtags)
            })

        except AttributeError as e:
            st.error(f"Error extracting post data: {e}")

    return posts


def analyze_lead_potential(content, keywords):
    """Analyze if content indicates a potential lead."""
    keyword_prompt = ", ".join(keywords)

    prompt = f"""
    Analyze the following LinkedIn post content. Determine if it indicates a potential client requirement for any products or services related to these keywords: {keyword_prompt}.

    Important:
    1. Classify as a potential lead ONLY if the post clearly indicates a need for external services without offering to provide those services themselves.
    2. Do not classify as a lead if the post is:
       - From a job seeker looking for employment
       - From an individual or company promoting or offering their own services
       - General informational content without a clear need for services
    3. Pay close attention to language that suggests the poster is offering services rather than seeking them.

    Post Content:
    {content}

    Respond with:
    1. 'True' if there's a potential lead (client looking for external services), or 'False' if not.
    2. A list of matched keywords (if any).
    3. A brief explanation for your decision, including the nature of the post (e.g., service request, job seeking, service promotion, or informational).

    Format your response as:
    Potential Lead: [True/False]
    Matched Keywords: [list of matched keywords]
    Explanation: [your explanation]
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system",
                 "content": "You are a helpful assistant that analyzes LinkedIn posts for lead potential, focusing on clear indications of need for external services while carefully distinguishing from promotional content."},
                {"role": "user", "content": prompt}
            ]
        )

        analysis = response.choices[0].message.content

        lines = analysis.split('\n')
        is_potential_lead = lines[0].split(':')[1].strip().lower() == 'true'
        matched_keywords = lines[1].split(':')[1].strip()
        explanation = lines[2].split(':')[1].strip()

        return is_potential_lead, matched_keywords, explanation
    except Exception as e:
        st.error(f"Error in lead potential analysis: {e}")
        return False, "", "Error in analysis"


def send_email(subject, body, sender_email, sender_password, recipient_email, attachments):
    """Send email with attachments."""
    try:
        message = MIMEMultipart()
        message['From'] = sender_email
        message['To'] = recipient_email
        message['Subject'] = subject

        message.attach(MIMEText(body, 'plain'))

        for attachment_file in attachments:
            with open(attachment_file, "rb") as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(attachment_file)}')
                message.attach(part)

        with smtplib.SMTP('smtp.gmail.com', 587) as session:
            session.starttls()
            session.login(sender_email, sender_password)
            text = message.as_string()
            session.sendmail(sender_email, recipient_email, text)

        return True

    except smtplib.SMTPAuthenticationError:
        st.error("SMTP Authentication Error: Please check your email and password in the .env file.")
    except smtplib.SMTPException as e:
        st.error(f"SMTP Error: {str(e)}")
    except Exception as e:
        st.error(f"An unexpected error occurred: {str(e)}")

    return False


def filter_duplicate_posts(posts):
    """Remove duplicate posts based on profile name, URL, and content."""
    seen = set()
    unique_posts = []
    for post in posts:
        post_key = (post['Profile Name'], post['Profile URL'], post['Content'][:100])
        if post_key not in seen:
            seen.add(post_key)
            unique_posts.append(post)
    return unique_posts


def main():
    """Main Streamlit application."""
    st.header("LinkedIn Lead Scraper")
    
    # Initialize session state
    if 'driver' not in st.session_state:
        st.session_state.driver = None
    if 'login_pending' not in st.session_state:
        st.session_state.login_pending = False
    if 'scraping_started' not in st.session_state:
        st.session_state.scraping_started = False

    # Sidebar for inputs
    with st.sidebar:
        st.text("")
        st.text("")
        
        # Login method selection
        manual_login = st.checkbox("🔐 Manual Login (Recommended)", value=True, 
                                   help="Opens browser for you to login manually, avoiding verification issues")
        
        if not manual_login:
            linkedin_username = st.text_input("LinkedIn Username", value="fatbatman85@gmail.com")
            linkedin_password = st.text_input("LinkedIn Password", type="password", value="makilesh")
        else:
            st.info("ℹ️ Browser will open. Login manually, then click 'Continue Scraping'")
            linkedin_username = ""
            linkedin_password = ""
            
        keywords = st.text_input("Keywords (comma-separated)", value="RWA, tokenization, blockchain")
        max_scroll_attempts = st.number_input("Max Scroll Attempts", min_value=1, value=5)
        
        if not st.session_state.login_pending:
            start_scraping = st.button("Start Scraping", use_container_width=True)
        else:
            start_scraping = False

    # Initialize or retrieve driver
    if start_scraping and st.session_state.driver is None:
        if not keywords:
            st.error("Please provide at least one keyword")
            st.stop()
            
        if not manual_login and (not linkedin_username or not linkedin_password):
            st.error("Please provide LinkedIn username and password")
            st.stop()

        chrome_options = Options()
        # Run in visible mode for debugging - comment this out to run headless
        # chrome_options.add_argument("--headless")  # Disabled for debugging
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-notifications")
        
        # Add a realistic user agent
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Anti-detection options
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2,
            "credentials_enable_service": False,
            "profile.password_manager_enabled": False
        })
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Execute anti-detection scripts
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {
            "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        st.info("✅ Chrome browser initialized")
        
        # Store driver in session state
        st.session_state.driver = driver
        st.session_state.keywords = keywords
        st.session_state.max_scroll_attempts = max_scroll_attempts
        st.session_state.manual_login = manual_login
        st.session_state.linkedin_username = linkedin_username if not manual_login else ""
        st.session_state.linkedin_password = linkedin_password if not manual_login else ""
        
        # Open login page for manual login
        if manual_login:
            st.info("🌐 Opening LinkedIn for manual login...")
            driver.get("https://www.linkedin.com/login")
            time.sleep(2)
            st.session_state.login_pending = True
            st.rerun()
    
    # Handle manual login flow
    if st.session_state.login_pending and st.session_state.driver is not None:
        driver = st.session_state.driver
        
        st.warning("⏸️ **Please login manually in the browser window**")
        st.markdown("### Steps:")
        st.markdown("1. ✅ Complete the login in the Chrome window")
        st.markdown("2. ✅ Complete any verification if requested")  
        st.markdown("3. ✅ Wait until you see your LinkedIn feed")
        st.markdown("4. ✅ Click the 'Continue Scraping' button below")
        
        # Wait for user confirmation
        continue_scraping = st.button("✅ Continue Scraping (I've logged in)", use_container_width=True, type="primary", key="continue_btn")
        
        if not continue_scraping:
            st.info("⏳ Waiting for you to login and click 'Continue Scraping'...")
            st.stop()
        
        # Verify login was successful
        current_url = driver.current_url
        st.info(f"Current URL: {current_url}")
        
        if "login" in current_url:
            st.error("❌ You don't appear to be logged in yet. Please complete the login and try again.")
            st.stop()
        
        st.success("✅ Login confirmed! Starting scraping...")
        st.session_state.login_pending = False
        st.session_state.scraping_started = True
        st.rerun()
    
    # Handle scraping
    if st.session_state.scraping_started and st.session_state.driver is not None:
        driver = st.session_state.driver
        keywords = st.session_state.keywords
        max_scroll_attempts = st.session_state.max_scroll_attempts
        manual_login = st.session_state.manual_login
        
        all_posts = []

        try:
            # For automatic login (not manual)
            if not manual_login:
                with st.spinner("Logging in to LinkedIn..."):
                    if not login_to_linkedin(driver, st.session_state.linkedin_username, st.session_state.linkedin_password):
                        st.stop()
                st.success("Successfully logged in to LinkedIn")

            keyword_list = [k.strip() for k in keywords.split(',')]

            for keyword in keyword_list:
                st.info(f"Searching for keyword: {keyword}")
                posts = search_and_scroll(driver, keyword, max_scroll_attempts)
                all_posts.extend(posts)
                time.sleep(random.uniform(5, 10))

            unique_posts = filter_duplicate_posts(all_posts)
            st.success(f"Total unique posts extracted: {len(unique_posts)}")

            if not unique_posts:
                st.warning("No posts found. Try different keywords or increase scroll attempts.")
                return

            with st.spinner("Analyzing lead potential..."):
                for post in unique_posts:
                    post['Is Potential Lead'], post['Matched Keywords'], post['Lead Analysis'] = analyze_lead_potential(
                        post['Content'], keyword_list)

            posts_df = pd.DataFrame(unique_posts)

            # Display all posts
            st.subheader("All Posts")
            st.dataframe(posts_df, use_container_width=True)

            # Save the complete DataFrame to an Excel file
            complete_filename = f"linkedin_posts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            posts_df.to_excel(complete_filename, index=False)

            # Filter to keep only the leads
            leads_df = posts_df[posts_df['Is Potential Lead'] == True]

            # Display leads
            st.subheader("Potential Leads")
            if not leads_df.empty:
                st.dataframe(leads_df, use_container_width=True)
            else:
                st.info("No potential leads found in the posts.")

            # Save the filtered DataFrame to an Excel file if it contains leads
            if not leads_df.empty:
                leads_filename = f"linkedin_leads_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                leads_df.to_excel(leads_filename, index=False)

                # Add download buttons
                col1, col2 = st.columns(2)
                with col1:
                    with open(complete_filename, "rb") as file:
                        st.download_button(
                            label="Download All Posts",
                            data=file.read(),
                            file_name=complete_filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                with col2:
                    with open(leads_filename, "rb") as file:
                        st.download_button(
                            label="Download Potential Leads",
                            data=file.read(),
                            file_name=leads_filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
            else:
                st.warning("No potential leads found.")
                # Add download button for all posts
                with open(complete_filename, "rb") as file:
                    st.download_button(
                        label="Download All Posts",
                        data=file.read(),
                        file_name=complete_filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

        except Exception as e:
            st.error(f"An error occurred: {e}")
            import traceback
            st.error(traceback.format_exc())
        finally:
            # Clean up driver and reset state
            try:
                if st.session_state.driver:
                    st.session_state.driver.quit()
            except:
                pass
            st.session_state.driver = None
            st.session_state.login_pending = False
            st.session_state.scraping_started = False
            gc.collect()
            
            st.success("✅ Scraping completed! Browser closed.")
            st.info("Click 'Start Scraping' to run again.")


if __name__ == "__main__":
    main()
