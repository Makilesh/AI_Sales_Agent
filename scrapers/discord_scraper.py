

import asyncio
from datetime import datetime

import discord
from discord.ext import commands

from models.lead import Lead
from scrapers.base import BaseScraper


class DiscordScraper(BaseScraper):
    """Scraper for Discord messages."""
    
    def __init__(
        self,
        bot_token: str,
        keywords: list[str],
        channel_ids: list[str],
        rate_limit: int = 50,
        days_filter: int = 30
    ) -> None:
        super().__init__(keywords, rate_limit, days_filter)
        self.bot_token = bot_token
        self.channel_ids = [int(cid) for cid in channel_ids if cid]
        self.client: discord.Client | None = None
        self._leads: list[Lead] = []
    
    async def _apply_rate_limit(self) -> None:
        """Apply rate limiting for Discord (requests per second)."""
        if self.last_request_time is None:
            self.last_request_time = datetime.now()
            return
        
        # Discord rate limit is per second, not per minute
        delay_seconds = 1.0 / self.rate_limit if self.rate_limit > 0 else 0.02
        
        elapsed = (datetime.now() - self.last_request_time).total_seconds()
        
        if elapsed < delay_seconds:
            wait_time = delay_seconds - elapsed
            await asyncio.sleep(wait_time)
        
        self.last_request_time = datetime.now()
        self._request_count += 1
        
    async def _initialize_client(self) -> None:
        """Initialize Discord client with intents."""
        if self.client is None:
            intents = discord.Intents.default()
            intents.message_content = True
            intents.guilds = True
            self.client = discord.Client(intents=intents)
    
    async def scrape(self) -> list[Lead]:
        """Scrape messages from specified Discord channels."""
        if not self.bot_token:
            print("Discord bot token not configured")
            return []
        
        if not self.channel_ids:
            print("No Discord channels configured")
            return []
        
        self._leads = []
        
        try:
            await self._initialize_client()
            
            # Start client and scrape
            await asyncio.wait_for(
                self._connect_and_scrape(),
                timeout=60.0  # Increased to 60 seconds for reliability
            )
        except asyncio.TimeoutError:
            print("Discord scraping timed out")
        except Exception as e:
            print(f"Error during Discord scraping: {e}")
        finally:
            if self.client and not self.client.is_closed():
                await self.client.close()
        
        return self._leads
    
    async def _connect_and_scrape(self) -> None:
        """Connect to Discord and scrape messages."""
        
        @self.client.event
        async def on_ready():
            """Called when bot is ready."""
            print(f"Discord bot connected as {self.client.user}")
            
            try:
                for channel_id in self.channel_ids:
                    await self._scrape_channel(channel_id)
            except Exception as e:
                print(f"Error scraping channels: {e}")
            finally:
                await self.client.close()
        
        @self.client.event
        async def on_error(event: str, *args, **kwargs):
            """Handle errors."""
            print(f"Discord error in {event}: {args}")
        
        # Start the client
        try:
            await self.client.start(self.bot_token)
        except discord.LoginFailure:
            print("Invalid Discord bot token")
        except Exception as e:
            print(f"Failed to connect to Discord: {e}")
    
    async def _scrape_channel(self, channel_id: int) -> None:
        """Scrape messages from a single channel."""
        try:
            await self._apply_rate_limit()
            
            channel = self.client.get_channel(channel_id)
            
            if channel is None:
                print(f"Channel {channel_id} not found or bot lacks access")
                return
            
            if not isinstance(channel, discord.TextChannel):
                print(f"Channel {channel_id} is not a text channel")
                return
            
            # Fetch recent messages (last 100)
            async for message in channel.history(limit=100):
                try:
                    lead = self._create_lead_from_message(message)
                    if lead:
                        self._leads.append(lead)
                except Exception as e:
                    print(f"Error processing message {message.id}: {e}")
                    continue
        
        except discord.Forbidden:
            print(f"Bot lacks permission to read channel {channel_id}")
        except Exception as e:
            print(f"Error scraping channel {channel_id}: {e}")
    
    def _create_lead_from_message(self, message: discord.Message) -> Lead | None:
        """Create a Lead object from a Discord message."""
        try:
            if not message.content or message.author.bot:
                return None
            
            # Check date filter
            if not self._is_within_date_range(message.created_at):
                return None
            
            # Get server and channel names
            guild_name = message.guild.name if message.guild else "DM"
            channel_name = message.channel.name if hasattr(message.channel, 'name') else "Unknown"
            
            # Discord removed discriminators in 2023, use display_name or name
            author_name = message.author.display_name or message.author.name
            
            return Lead(
                source='discord',
                author=author_name,
                content=message.content,
                timestamp=message.created_at,
                url=message.jump_url,
                engagement_score=len(message.reactions) if message.reactions else 0,
                channel_name=channel_name,
                metadata={
                    'message_id': str(message.id),
                    'channel_id': str(message.channel.id),
                    'guild_name': guild_name,
                    'guild_id': str(message.guild.id) if message.guild else None,
                    'has_attachments': len(message.attachments) > 0,
                    'reply_to': str(message.reference.message_id) if message.reference else None
                }
            )
        except Exception as e:
            print(f"Error creating lead from message: {e}")
            return None
    
    def __repr__(self) -> str:
        return f"DiscordScraper(channels={len(self.channel_ids)}, keywords={len(self.keywords)})"
