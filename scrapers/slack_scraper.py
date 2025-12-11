

import asyncio
from datetime import datetime

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from models.lead import Lead
from scrapers.base import BaseScraper


class SlackScraper(BaseScraper):
    """Scraper for Slack messages."""
    
    def __init__(
        self,
        bot_token: str,
        keywords: list[str],
        channel_ids: list[str],
        rate_limit: int = 1,
        days_filter: int = 30
    ) -> None:
        super().__init__(keywords, rate_limit, days_filter)
        self.bot_token = bot_token
        self.channel_ids = channel_ids
        
        try:
            self.client = WebClient(token=bot_token)
        except Exception as e:
            raise ValueError(f"Failed to initialize Slack client: {e}")
    
    async def _apply_rate_limit(self) -> None:
        """Apply rate limiting for Slack (requests per second)."""
        if self.last_request_time is None:
            self.last_request_time = datetime.now()
            return
        
        # Slack rate limit is per second, not per minute
        delay_seconds = 1.0 / self.rate_limit if self.rate_limit > 0 else 1.0
        
        elapsed = (datetime.now() - self.last_request_time).total_seconds()
        
        if elapsed < delay_seconds:
            wait_time = delay_seconds - elapsed
            await asyncio.sleep(wait_time)
        
        self.last_request_time = datetime.now()
        self._request_count += 1
    
    async def scrape(self) -> list[Lead]:
        """Scrape messages from specified Slack channels."""
        if not self.bot_token:
            print("Slack bot token not configured")
            return []
        
        if not self.channel_ids:
            print("No Slack channels configured")
            return []
        
        all_leads: list[Lead] = []
        
        for channel_id in self.channel_ids:
            try:
                leads = await self._scrape_channel(channel_id)
                all_leads.extend(leads)
            except Exception as e:
                print(f"Error scraping channel {channel_id}: {e}")
                continue
        
        return all_leads
    
    async def _scrape_channel(self, channel_id: str) -> list[Lead]:
        """Scrape messages from a single Slack channel."""
        leads: list[Lead] = []
        
        try:
            await self._apply_rate_limit()
            
            # Get channel info
            channel_info = await asyncio.to_thread(
                self.client.conversations_info,
                channel=channel_id
            )
            channel_name = channel_info.get('channel', {}).get('name', 'Unknown')
            
            # Fetch conversation history with pagination
            cursor = None
            messages_fetched = 0
            max_messages = 200
            
            while messages_fetched < max_messages:
                await self._apply_rate_limit()
                
                response = await asyncio.to_thread(
                    self.client.conversations_history,
                    channel=channel_id,
                    limit=100,
                    cursor=cursor
                )
                
                messages = response.get('messages', [])
                
                if not messages:
                    break
                
                # Process messages
                for message in messages:
                    try:
                        lead = await self._create_lead_from_message(
                            message, 
                            channel_id, 
                            channel_name
                        )
                        if lead:
                            leads.append(lead)
                    except Exception as e:
                        print(f"Error processing message: {e}")
                        continue
                
                messages_fetched += len(messages)
                
                # Check if there are more messages
                cursor = response.get('response_metadata', {}).get('next_cursor')
                if not cursor:
                    break
        
        except SlackApiError as e:
            print(f"Slack API error for channel {channel_id}: {e.response['error']}")
        except Exception as e:
            print(f"Error scraping Slack channel {channel_id}: {e}")
        
        return leads
    
    async def _create_lead_from_message(
        self, 
        message: dict, 
        channel_id: str,
        channel_name: str
    ) -> Lead | None:
        """Create a Lead object from a Slack message."""
        try:
            # Skip bot messages and messages without text
            if message.get('bot_id') or not message.get('text'):
                return None
            
            user_id = message.get('user', 'Unknown')
            
            # Get user info for better lead data (async to avoid blocking)
            try:
                user_info = await asyncio.to_thread(self.client.users_info, user=user_id)
                username = user_info.get('user', {}).get('real_name') or user_info.get('user', {}).get('name', user_id)
            except Exception:
                username = user_id
            
            # Convert timestamp to datetime
            ts = float(message.get('ts', 0))
            timestamp = datetime.fromtimestamp(ts)
            
            # Check date filter
            if not self._is_within_date_range(timestamp):
                return None
            
            # Build message URL
            team_id = message.get('team')
            url = f"https://slack.com/app_redirect?channel={channel_id}&message_ts={message.get('ts')}"
            
            # Count reactions
            reactions = message.get('reactions', [])
            engagement_score = sum(r.get('count', 0) for r in reactions)
            
            return Lead(
                source='slack',
                author=username,
                content=message.get('text', ''),
                timestamp=timestamp,
                url=url,
                engagement_score=engagement_score,
                channel_name=channel_name,
                metadata={
                    'message_ts': message.get('ts'),
                    'channel_id': channel_id,
                    'user_id': user_id,
                    'team_id': team_id,
                    'thread_ts': message.get('thread_ts'),
                    'reply_count': message.get('reply_count', 0),
                    'has_files': bool(message.get('files'))
                }
            )
        except Exception as e:
            print(f"Error creating lead from Slack message: {e}")
            return None
    
    def __repr__(self) -> str:
        return f"SlackScraper(channels={len(self.channel_ids)}, keywords={len(self.keywords)})"
