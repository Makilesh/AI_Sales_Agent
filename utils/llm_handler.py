"""LLM-based lead qualification using OpenAI GPT-4-turbo with Gemini fallback.

STRICT QUALIFICATION: Only qualifies leads where someone is ACTIVELY SEEKING our services.
Not discussions, news, opinions, or educational content - only service inquiries.
"""

import json
import asyncio
from typing import Optional

from decouple import config
from openai import OpenAI
from openai import OpenAIError
import google.generativeai as genai

from models.lead import Lead


class LLMLeadQualifier:
    """Qualify leads using GPT-4-turbo. ONLY qualifies leads where someone is ACTIVELY SEEKING our services (not just discussing topics)."""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4-turbo", target_service: Optional[str] = None):
        """
        Initialize LLM qualifier with OpenAI and Gemini fallback.
        
        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY from .env)
            model: Model to use (default: gpt-4-turbo)
            target_service: Specific service to filter for (e.g., 'RWA', 'Crypto', 'AI/ML', 'Blockchain')
        """
        self.api_key = api_key or config("OPENAI_API_KEY", default="")
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY in .env file.")
        
        self.model = model
        self.target_service = target_service
        self.client = OpenAI(api_key=self.api_key)
        
        # Initialize Gemini as fallback
        self.gemini_api_key = config("GEMINI_API_KEY", default="")
        self.gemini_model = None
        if self.gemini_api_key:
            try:
                genai.configure(api_key=self.gemini_api_key)
                # Use gemini-2.5-flash (fast and cost-effective)
                self.gemini_model = genai.GenerativeModel('gemini-2.5-flash')
                print("✅ Gemini 2.5 Flash fallback configured successfully")
            except Exception as e:
                print(f"⚠️ Gemini fallback unavailable: {str(e)}")
                self.gemini_model = None
    
    def _build_qualification_prompt(self, lead: Lead) -> str:
        """Build strict qualification prompt - only accept explicit service requests."""
        content = lead.content[:2000]
        title = lead.title or ""
        full_text = f"{title}\n\n{content}" if title else content
        
        # Service-specific filtering instructions
        service_focus = ""
        if self.target_service:
            service_focus = f"""
**🎯 MANDATORY FILTER: {self.target_service.upper()} SERVICE ONLY**

You MUST ONLY qualify leads asking for {self.target_service} service specifically.
- If asking for {self.target_service}: Check if qualified using rules below
- If asking for OTHER services: Automatically set is_qualified=false, confidence=0.0
- If unclear which service: Set confidence=0.3 max

REJECT leads about other services even if they're high-quality inquiries.
"""
        
        # Competitor detection
        competitor_context = self._detect_competitor_mentions(full_text)

        # IMPROVED (ISSUE #1): Reddit metadata boost for targeted search leads
        reddit_boost_context = ""
        if lead.source == 'reddit' and lead.metadata.get('targeted_search'):
            search_phrase = lead.metadata.get('search_phrase', 'unknown')
            reddit_boost_context = f"""🎯 **HIGH-INTENT SEARCH LEAD:**
This lead was found via targeted Reddit search for: "{search_phrase}"
This indicates ACTIVE service-seeking behavior (not just browsing subreddit).

**QUALIFICATION BOOST:** Increase confidence by +0.15 if this is a genuine service inquiry.
Search-targeted leads have 3x higher conversion rates than general subreddit posts.
"""

        prompt = f"""You are qualifying sales leads for Shamla Tech (India-based Web3/RWA tokenization firm). ONLY qualify if someone is ACTIVELY SEEKING our services.

**OUR SERVICES (Shamla Tech):**
- RWA Tokenization: Tokenizing real-world assets on blockchain
- Crypto/Web3: DeFi, Web3 apps, smart contracts, crypto integration  
- Blockchain: Custom blockchain, distributed ledger, consensus
- AI/ML: AI automation, ML models, chatbots, neural networks

**OUR DIRECT COMPETITORS (India-based Web3/Blockchain firms):**
- Antier Solutions, Accubits Technologies, Somish Blockchain Labs
- LeewayHertz, Primafelicitas, SoluLab, IdeaUsher, Tech Alchemy, Codezeros
- NetSet Software, Nadcab Labs, Dev Technosys, RedDuck, Quytech

{competitor_context}

{reddit_boost_context}

{service_focus}

**Lead Content:**
{full_text}

**QUALIFICATION RULES:**

✅ HIGH CONFIDENCE (0.8-1.0) - QUALIFY ONLY IF:
1. Contains help-seeking phrase (at least one required):
   • "looking for [service/consultant/agency/solution/platform]"
   • "need help [with/implementing/building]"
   • "recommend a [service/tool/platform/consultant]"
   • "anyone know [a good/any/where to find]"
   • "seeking [expert/consultant/developer/agency]"
   • "can someone help me [with/find]"
   • "suggestions for [service/platform/tool]"
   • "best [platform/service/tool] for"
   • "who can help [me/us] with"
   • "where can I find [service/consultant]"

2. AND describes a problem/need related to our services

3. AND is clearly asking for external help (not DIY/learning)

Example QUALIFIED leads:
✓ "Looking for a blockchain consultant to help tokenize our real estate portfolio"
✓ "Need help implementing DeFi protocol, any recommendations?"
✓ "Anyone know a good RWA platform for asset tokenization?"
✓ "Seeking AI automation expert to build chatbot for customer service"
✓ "Best service for tokenizing real estate assets?"
✓ "Can someone help me find a Web3 developer for our project?"

✅ **PRIORITY LEADS - Competitor Frustration:**
✓ "Antier Solutions too expensive, need cheaper RWA tokenization alternative"
✓ "LeewayHertz delayed our project 3 months, looking for reliable blockchain consultant"
✓ "Disappointed with Accubits, anyone know better Web3 agency?"
✓ "Alternative to SoluLab? Their tokenization platform not working"
✓ "Need to replace our current Web3 vendor (Primafelicitas), recommendations?"
✓ "Switching from Codezeros - too slow, need responsive blockchain developer"

**These get +0.2 confidence boost** as they're actively seeking to change providers!

⚠️ MODERATE (0.4-0.7) - UNCERTAIN:
- Asks vague "how to" without clearly seeking service
- Discusses challenges but doesn't explicitly ask for help
- Educational questions that might lead to service need
- Mentions considering hiring but unclear

❌ LOW (0.0-0.3) - DO NOT QUALIFY:
- Just discussing/learning about topic (no help request)
- Sharing news, articles, opinions, updates
- Promoting their own product/service
- Explaining concepts to others
- General questions without seeking service
- Announcing their own solution/launch

Example NOT QUALIFIED:
✗ "RWA tokenization is revolutionizing real estate" → opinion/discussion
✗ "Just learned about blockchain, so cool!" → learning/excitement
✗ "Our new RWA platform just launched, check it out!" → self-promotion
✗ "How does tokenization work?" → educational question, not service request
✗ "Tokenization could transform real estate investing" → speculation/opinion
✗ "Excited to announce our blockchain solution!" → announcement

**CRITICAL RULES:**
1. Be STRICT - only qualify if EXPLICITLY asking for external service/help
2. Quote the exact help-seeking phrase found in your reason
3. If no help-seeking phrase present → is_qualified=false
4. Discussions about topics ≠ asking for service
5. Learning/curiosity ≠ service inquiry

Response JSON (no markdown):
{{
  "is_qualified": true/false,
  "confidence_score": 0.0-1.0,
  "reason": "Quote specific help-seeking phrase found, or explain why not qualified (1-2 sentences)",
  "service_match": ["RWA Tokenization"] or ["Crypto/Web3"] or ["Blockchain"] or ["AI/ML"] or []
}}"""
        
        return prompt
    
    def _detect_competitor_mentions(self, text: str) -> str:
        """
        Detect mentions of direct competitors and frustration signals.
        
        Returns:
            str: Context string for LLM about competitor mentions (empty if none)
        """
        if not text:
            return ""
        
        text_lower = text.lower()
        
        # Shamla Tech competitors
        competitors = [
            "antier", "antier solutions",
            "accubits", "accubits technologies",
            "somish", "somish blockchain",
            "leewayhertz", "leeway hertz",
            "primafelicitas",
            "solulab",
            "ideausher",
            "tech alchemy",
            "codezeros",
            "netset", "netset software",
            "nadcab", "nadcab labs",
            "dev technosys",
            "redduck",
            "quytech",
            "owebest",
            "taksh it"
        ]
        
        # Find mentioned competitors
        mentioned = [comp for comp in competitors if comp in text_lower]
        
        if not mentioned:
            return ""
        
        # Check for frustration signals
        frustration_signals = [
            "expensive", "overpriced", "too much", "costly",
            "slow", "delay", "delayed", "late", "unresponsive",
            "problem", "issue", "trouble", "struggling",
            "disappointed", "frustrated", "unhappy", "dissatisfied",
            "not working", "doesn't work", "failed",
            "alternative to", "better than", "cheaper than",
            "replace", "switch from", "looking for new",
            "need new", "change provider", "vendor change"
        ]
        
        has_frustration = any(signal in text_lower for signal in frustration_signals)
        
        if has_frustration:
            competitor_names = ", ".join(mentioned)
            return f"""🎯 **HIGH-PRIORITY LEAD DETECTED:**
This lead mentions competitor(s): {competitor_names}
AND shows frustration/dissatisfaction signals.

**QUALIFICATION BOOST:** Increase confidence by +0.2 if this is a genuine service inquiry.
They are actively looking for alternatives to their current provider - prime conversion opportunity!
"""
        else:
            # Just mentions competitor without frustration
            competitor_names = ", ".join(mentioned)
            return f"ℹ️ Note: Lead mentions competitor: {competitor_names} (no frustration signals detected)"
    
    def _contains_help_seeking_phrase(self, text: str) -> tuple[bool, str]:
        """
        Check if text contains help-seeking phrases that indicate service inquiry.
        
        Uses FLEXIBLE patterns for Reddit/casual platforms (includes imperative forms).
        
        Returns:
            tuple: (has_phrase: bool, matched_phrase: str)
        """
        if not text:
            return False, ""
        
        text_lower = text.lower()
        
        # FLEXIBLE help-seeking patterns (Reddit/casual appropriate)
        help_patterns = [
            # Direct requests (with or without "I/we")
            ("looking for", "looking for"),
            ("need advice", "need advice"),
            ("need help", "need help"),
            ("need guidance", "need guidance"),
            ("need suggestions", "need suggestions"),
            ("need recommendations", "need recommendations"),
            ("seeking advice", "seeking advice"),
            ("seeking help", "seeking help"),
            ("seeking recommendations", "seeking recommendations"),
            
            # Question forms (common on Reddit)
            ("any advice", "any advice"),
            ("any suggestions", "any suggestions"),
            ("any recommendations", "any recommendations"),
            ("anyone recommend", "anyone recommend"),
            ("anyone suggest", "anyone suggest"),
            ("anyone know", "anyone know"),
            ("does anyone", "does anyone"),
            ("can someone", "can someone"),
            ("who can help", "who can help"),
            ("where can i", "where can i"),
            ("how do i", "how do i"),
            ("what should i", "what should i"),
            
            # Imperative/casual (Reddit style)
            ("help me", "help me"),
            ("help needed", "help needed"),
            ("advice needed", "advice needed"),
            ("recommendations needed", "recommendations needed"),
            ("suggestions welcome", "suggestions welcome"),
            
            # Evaluation phrases
            ("looking to hire", "looking to hire"),
            ("considering", "considering"),
            ("evaluating", "evaluating"),
            ("exploring options", "exploring options"),
            
            # Which/best questions (buying signals)
            ("which is best", "which is best"),
            ("what's the best", "what's the best"),
            ("whats the best", "whats the best"),
            ("best way to", "best way to"),
            ("best solution", "best solution"),
            ("best platform", "best platform")
        ]
        
        for pattern, match_name in help_patterns:
            if pattern in text_lower:
                return True, match_name
        
        return False, ""
    
    def _is_obvious_non_inquiry(self, text: str) -> bool:
        """
        Quick filter for obvious spam/promotion/news that should never qualify.
        Only rejects OBVIOUS non-inquiries to reduce false negatives.
        
        Returns True if content is definitely not an inquiry.
        """
        if not text:
            return True
        
        text_lower = text.lower()
        
        # Obvious spam/promotion indicators
        spam_indicators = [
            "check out our", "our platform offers", "we provide services",
            "proud to announce", "join our webinar", "register now",
            "click here", "buy now", "limited time offer",
            "visit our website", "dm for more", "link in bio"
        ]
        
        # Obvious job postings (hiring, not seeking service)
        hiring_indicators = [
            "we are hiring", "we're hiring", "job opening",
            "apply now", "submit your resume", "send cv to",
            "position available", "now accepting applications"
        ]
        
        # Check for multiple spam indicators
        spam_count = sum(1 for indicator in spam_indicators if indicator in text_lower)
        hiring_count = sum(1 for indicator in hiring_indicators if indicator in text_lower)
        
        # If multiple spam/hiring indicators, definitely not inquiry
        if spam_count >= 2 or hiring_count >= 2:
            return True
        
        return False
    
    def _has_implicit_inquiry_signals(self, text: str) -> bool:
        """
        Check for implicit signals that suggest service inquiry without explicit help phrases.
        
        Examples of implicit inquiries:
        - "Struggling with tokenization implementation"
        - "Our RWA platform needs smart contract integration"
        - "Real estate tokenization budget: $50k"
        - "Anyone experienced with asset tokenization?"
        
        Returns True if content has inquiry signals worth LLM evaluation.
        """
        if not text:
            return False
        
        text_lower = text.lower()
        
        # Implicit inquiry signals
        inquiry_signals = [
            # Problem statements (often lead to service requests)
            "struggling with", "having trouble", "can't figure out",
            "issues with", "problems with", "challenge with",
            "difficulty with", "stuck on", "blocked by",
            
            # Evaluation/consideration phrases
            "considering hiring", "thinking about", "planning to",
            "budget for", "budget:", "price range", "cost estimate",
            "willing to pay", "looking to invest",
            
            # Question forms that imply seeking solution
            "has anyone", "anyone experienced", "anyone here",
            "anyone tried", "anyone worked with",
            
            # Resource/tool seeking (implicit help)
            "what tool", "which platform", "which service",
            "recommend", "suggestion", "advice",
            
            # Business need statements
            "we need", "i need", "our company needs",
            "our project requires", "requirement for",
            "must have", "essential to have"
        ]
        
        # Count signals
        signal_count = sum(1 for signal in inquiry_signals if signal in text_lower)
        
        # If 2+ signals, worth sending to LLM
        return signal_count >= 2
    
    def _is_service_inquiry(self, text: str) -> bool:
        """
        Validate that content is truly a service inquiry (not news/discussion/promotion).
        
        Returns True only if:
        1. Contains help-seeking phrase
        2. Does NOT contain anti-patterns (news, self-promotion, education)
        """
        if not text:
            return False
        
        text_lower = text.lower()
        
        # Check for help-seeking phrase first
        has_help_phrase, _ = self._contains_help_seeking_phrase(text)
        if not has_help_phrase:
            return False
        
        # Anti-patterns that disqualify even if help phrase found
        # ONLY block obvious spam/promotion/hiring, not legitimate inquiries
        anti_patterns = [
            # Self-promotion (clear spam)
            "check out our", "our platform offers", 
            "we provide services", "proud to announce",
            "join our webinar", "register now",
            
            # Job postings (hiring language)
            "we are hiring", "we're hiring", "job opening",
            "apply now", "submit your resume", "send cv",
            "job title:", "position:", "salary:", "duration:",
            "experience:", "years experience", "yrs exp",
            "location:", "contract position", "full-time",
            "part-time", "freelance opportunity"
        ]
        
        # If contains anti-pattern, it's likely not a genuine inquiry
        for pattern in anti_patterns:
            if pattern in text_lower:
                return False
        
        return True
    
    def _call_gemini(self, prompt: str, lead: Lead = None) -> dict:
        """
        Call Gemini API as fallback when OpenAI fails.
        Uses simplified prompt to avoid recitation blocking.
        
        Args:
            prompt: The qualification prompt (may not be used to avoid recitation)
            lead: The original Lead object (used to extract content directly)
            
        Returns:
            dict: Qualification result matching OpenAI format
        """
        if not self.gemini_model:
            raise Exception("Gemini not configured. Set GEMINI_API_KEY in .env")
        
        try:
            # Build ultra-simple prompt to avoid recitation blocking
            # Don't use the long OpenAI prompt - it triggers recitation
            if lead:
                lead_text = f"{lead.title}\n\n{lead.content}" if lead.title else lead.content
                lead_text = lead_text[:800]  # Limit length
            else:
                # Fallback: extract from prompt
                content_start = prompt.find("**Lead Content:**")
                if content_start != -1:
                    rules_start = prompt.find("**QUALIFICATION RULES:**")
                    lead_text = prompt[content_start:rules_start].replace("**Lead Content:**", "").strip()[:800]
                else:
                    lead_text = prompt[:800]
            
            # Simple, direct prompt (no long instructions that might trigger recitation)
            # Keep it as simple and direct as the working test prompts
            gemini_prompt = f'"{lead_text}" - Is this seeking RWA/Crypto/Blockchain/AI services? JSON: {{"is_qualified": true/false, "confidence_score": 0.0-1.0, "reason": "why", "service_match": ["services"]}}'

            # Call Gemini with relaxed safety settings
            from google.generativeai.types import HarmCategory, HarmBlockThreshold
            
            response = self.gemini_model.generate_content(
                gemini_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,
                    max_output_tokens=300,
                ),
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                }
            )
            
            # Check if response was blocked
            if not response.parts:
                finish_reason = response.candidates[0].finish_reason if response.candidates else "UNKNOWN"
                safety_ratings = response.candidates[0].safety_ratings if response.candidates else []
                raise Exception(f"Gemini blocked response. Finish reason: {finish_reason}, Safety: {safety_ratings}")
            
            # Parse response - Gemini with JSON mime type returns text that needs parsing
            result_text = response.text.strip()
            
            # Extract JSON from response (Gemini sometimes adds text before/after)
            # Try to find JSON object in the response
            json_start = result_text.find('{')
            json_end = result_text.rfind('}')
            
            if json_start != -1 and json_end != -1:
                result_text = result_text[json_start:json_end+1]
            
            # Try to parse as JSON
            try:
                result = json.loads(result_text)
            except json.JSONDecodeError:
                # If JSON parsing fails, try cleaning markdown
                if result_text.startswith("```json"):
                    result_text = result_text[7:]
                if result_text.startswith("```"):
                    result_text = result_text[3:]
                if result_text.endswith("```"):
                    result_text = result_text[:-3]
                result_text = result_text.strip()
                
                # Try again after cleaning
                json_start = result_text.find('{')
                json_end = result_text.rfind('}')
                if json_start != -1 and json_end != -1:
                    result_text = result_text[json_start:json_end+1]
                
                result = json.loads(result_text)
            
            # Validate structure
            required_keys = {"is_qualified", "confidence_score", "reason", "service_match"}
            if not required_keys.issubset(result.keys()):
                return {
                    "is_qualified": False,
                    "confidence_score": 0.0,
                    "reason": "Invalid response structure from Gemini",
                    "service_match": [],
                    "error": "Missing required keys in Gemini response"
                }
            
            # Ensure correct types
            result["is_qualified"] = bool(result["is_qualified"])
            result["confidence_score"] = float(result["confidence_score"])
            result["reason"] = str(result["reason"])
            result["service_match"] = list(result["service_match"]) if result["service_match"] else []
            
            # Clamp confidence score
            result["confidence_score"] = max(0.0, min(1.0, result["confidence_score"]))
            
            # Add note that Gemini was used
            result["llm_provider"] = "gemini"
            
            return result
            
        except json.JSONDecodeError as e:
            # Include the actual response text in error for debugging
            raw_response = response.text if 'response' in locals() else "No response"
            raise Exception(f"Gemini JSON parse error: {str(e)}. Raw response: {raw_response[:500]}")
        except Exception as e:
            raise Exception(f"Gemini API call failed: {str(e)}")
    
    def qualify_lead(self, lead: Lead) -> dict:
        """
        Qualify a lead using strict validation + GPT-4-turbo.
        
        Pre-validates content for help-seeking phrases before expensive LLM call.
        NOW WITH RELAXED VALIDATION: Allows implicit service inquiries through to LLM.
        
        Args:
            lead: Lead object to qualify
            
        Returns:
            dict with:
                - is_qualified (bool): Whether lead is qualified
                - confidence_score (float): Confidence 0.0-1.0
                - reason (str): Explanation with quoted phrase
                - service_match (list): Matching services
                - skipped_llm (bool, optional): True if LLM call was skipped
                - error (str, optional): Error message if failed
        """
        # RELAXED PRE-VALIDATION: Only skip obvious non-inquiries
        # Let LLM evaluate borderline cases instead of pre-filtering
        
        # Quick rejection: obvious spam/promotion/news
        if self._is_obvious_non_inquiry(lead.content):
            return {
                "is_qualified": False,
                "confidence_score": 0.0,
                "reason": "Content is spam/promotion/news, not inquiry",
                "service_match": [],
                "skipped_llm": True
            }
        
        # Check for explicit help-seeking phrases
        has_help_phrase, matched_phrase = self._contains_help_seeking_phrase(lead.content)
        
        # CHANGED: Instead of hard rejection, just add context for LLM
        # Let borderline cases through to LLM for evaluation
        if not has_help_phrase:
            # Still check for implicit inquiry signals
            if self._has_implicit_inquiry_signals(lead.content):
                # Let LLM decide - could be valid implicit inquiry
                pass  # Continue to LLM call
            else:
                # No explicit or implicit signals - likely just discussion
                return {
                    "is_qualified": False,
                    "confidence_score": 0.0,
                    "reason": "No help-seeking phrase or inquiry signals detected",
                    "service_match": [],
                    "skipped_llm": True
                }
        
        # If validations pass, proceed with LLM call
        try:
            prompt = self._build_qualification_prompt(lead)
            
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a strict sales lead qualifier. Only qualify leads where someone explicitly asks for services. Respond with valid JSON only."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.2,  # Low temperature for consistent strict filtering
                max_tokens=300,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            result_text = response.choices[0].message.content.strip()
            
            # Remove markdown if present
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.startswith("```"):
                result_text = result_text[3:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()
            
            result = json.loads(result_text)
            
            # Validate structure
            required_keys = {"is_qualified", "confidence_score", "reason", "service_match"}
            if not required_keys.issubset(result.keys()):
                return {
                    "is_qualified": False,
                    "confidence_score": 0.0,
                    "reason": "Invalid response structure from LLM",
                    "service_match": [],
                    "error": "Missing required keys in LLM response"
                }
            
            # Ensure correct types
            result["is_qualified"] = bool(result["is_qualified"])
            result["confidence_score"] = float(result["confidence_score"])
            result["reason"] = str(result["reason"])
            result["service_match"] = list(result["service_match"]) if result["service_match"] else []
            
            # Clamp confidence score
            result["confidence_score"] = max(0.0, min(1.0, result["confidence_score"]))
            
            # Mark that OpenAI was used
            result["llm_provider"] = "openai"
            
            return result
            
        except OpenAIError as e:
            # Try Gemini as fallback
            if self.gemini_model:
                print(f"⚠️ OpenAI failed ({str(e)[:50]}...), trying Gemini fallback...")
                try:
                    return self._call_gemini(prompt, lead=lead)
                except Exception as gemini_error:
                    return {
                        "is_qualified": False,
                        "confidence_score": 0.0,
                        "reason": f"Both OpenAI and Gemini failed. OpenAI: {str(e)}, Gemini: {str(gemini_error)}",
                        "service_match": [],
                        "error": f"OpenAI: {str(e)}, Gemini: {str(gemini_error)}"
                    }
            else:
                return {
                    "is_qualified": False,
                    "confidence_score": 0.0,
                    "reason": f"OpenAI API error: {str(e)}",
                    "service_match": [],
                    "error": str(e)
                }
        
        except json.JSONDecodeError as e:
            return {
                "is_qualified": False,
                "confidence_score": 0.0,
                "reason": f"Failed to parse LLM response: {str(e)}",
                "service_match": [],
                "error": f"JSON parse error: {str(e)}"
            }
        
        except Exception as e:
            return {
                "is_qualified": False,
                "confidence_score": 0.0,
                "reason": f"Unexpected error: {str(e)}",
                "service_match": [],
                "error": str(e)
            }
    
    def batch_qualify_leads(self, leads: list[Lead], max_leads: Optional[int] = None) -> list[dict]:
        """
        Qualify multiple leads in batch (sequential).
        
        Args:
            leads: List of Lead objects
            max_leads: Maximum number of leads to process (for cost control)
            
        Returns:
            List of qualification results with lead info
        """
        results = []
        process_count = min(len(leads), max_leads) if max_leads else len(leads)
        
        print(f"🤖 Starting LLM qualification for {process_count} leads...")
        
        for idx, lead in enumerate(leads[:process_count], 1):
            print(f"  [{idx}/{process_count}] Qualifying: {lead.author}...")
            
            qualification = self.qualify_lead(lead)
            
            # Add lead reference
            result = {
                "lead_url": lead.url,
                "lead_author": lead.author,
                "lead_source": lead.source,
                **qualification
            }
            
            results.append(result)
            
            # Print result
            status = "✅ QUALIFIED" if qualification["is_qualified"] else "❌ Not qualified"
            confidence = qualification["confidence_score"]
            print(f"     {status} (confidence: {confidence:.2f})")
        
        # Summary
        qualified_count = sum(1 for r in results if r["is_qualified"])
        print(f"\n✅ Qualification complete: {qualified_count}/{process_count} leads qualified")
        
        return results
    
    async def qualify_lead_async(self, lead: Lead, idx: int, total: int) -> dict:
        """
        Qualify a lead asynchronously with progress indicator.
        
        Args:
            lead: Lead object to qualify
            idx: Current lead index (1-based)
            total: Total number of leads
            
        Returns:
            dict with qualification results and lead info
        """
        print(f"  Qualifying lead {idx}/{total}...")
        
        # Run synchronous qualify_lead in thread pool
        qualification = await asyncio.to_thread(self.qualify_lead, lead)
        
        # Add lead reference
        result = {
            "lead_url": lead.url,
            "lead_author": lead.author,
            "lead_source": lead.source,
            **qualification
        }
        
        return result
    
    async def qualify_leads_concurrent(
        self, 
        leads: list[Lead], 
        max_concurrent: int = 5,
        max_leads: Optional[int] = None
    ) -> list[dict]:
        """
        Qualify multiple leads concurrently with rate limiting.
        
        Args:
            leads: List of Lead objects
            max_concurrent: Maximum concurrent API requests
            max_leads: Maximum total leads to process (for cost control)
            
        Returns:
            List of qualification results in same order as input leads
        """
        process_count = min(len(leads), max_leads) if max_leads else len(leads)
        leads_to_process = leads[:process_count]
        
        print(f"🤖 Starting concurrent LLM qualification for {process_count} leads...")
        print(f"   Max concurrent requests: {max_concurrent}")
        
        # Create semaphore for rate limiting
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def qualify_with_semaphore(lead: Lead, idx: int) -> dict:
            async with semaphore:
                return await self.qualify_lead_async(lead, idx, process_count)
        
        # Create tasks for all leads
        tasks = [
            qualify_with_semaphore(lead, idx)
            for idx, lead in enumerate(leads_to_process, 1)
        ]
        
        # Run all tasks concurrently (but limited by semaphore)
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions
        final_results = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                # Create error result for failed leads
                lead = leads_to_process[idx]
                final_results.append({
                    "lead_url": lead.url,
                    "lead_author": lead.author,
                    "lead_source": lead.source,
                    "is_qualified": False,
                    "confidence_score": 0.0,
                    "reason": f"Processing error: {str(result)}",
                    "service_match": [],
                    "error": str(result)
                })
            else:
                final_results.append(result)
        
        # Summary
        qualified_count = sum(1 for r in final_results if r.get("is_qualified", False))
        skipped_llm_count = sum(1 for r in final_results if r.get("skipped_llm", False))
        llm_called = process_count - skipped_llm_count
        
        print(f"\n✅ Qualification complete: {qualified_count}/{process_count} leads qualified")
        if skipped_llm_count > 0:
            print(f"   💰 API savings: {skipped_llm_count}/{process_count} leads filtered by pre-validation (LLM called: {llm_called})")
        
        return final_results


# Convenience functions

def qualify_lead(lead: Lead, target_service: Optional[str] = None) -> dict:
    """
    Qualify a single lead using GPT-4-turbo.
    
    Args:
        lead: Lead object to qualify
        target_service: Optional service filter (e.g., 'RWA', 'Crypto')
        
    Returns:
        dict with qualification results
    """
    qualifier = LLMLeadQualifier(target_service=target_service)
    return qualifier.qualify_lead(lead)


def qualify_leads_batch(leads: list[Lead], max_leads: Optional[int] = None, target_service: Optional[str] = None) -> list[dict]:
    """
    Qualify multiple leads in batch (sequential).
    
    Args:
        leads: List of Lead objects
        max_leads: Maximum number to process
        target_service: Optional service filter
        
    Returns:
        List of qualification results
    """
    qualifier = LLMLeadQualifier(target_service=target_service)
    return qualifier.batch_qualify_leads(leads, max_leads)


async def qualify_leads_concurrent(
    leads: list[Lead], 
    max_concurrent: int = 5,
    max_leads: Optional[int] = None,
    target_service: Optional[str] = None
) -> list[dict]:
    """
    Qualify multiple leads concurrently using asyncio.
    
    Args:
        leads: List of Lead objects
        max_concurrent: Maximum concurrent API requests (default: 5)
        max_leads: Maximum total leads to process (for cost control)
        target_service: Filter for specific service (e.g., 'RWA', 'Crypto', 'AI/ML', 'Blockchain')
        
    Returns:
        List of qualification results in same order as input leads
        
    Example:
        results = await qualify_leads_concurrent(leads, max_concurrent=5, max_leads=20, target_service='RWA')
    """
    qualifier = LLMLeadQualifier(target_service=target_service)
    return await qualifier.qualify_leads_concurrent(leads, max_concurrent, max_leads)
