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
        """Lean qualification prompt - 300 tokens max, no examples."""
        # OPTIMIZED: Use first 300 chars only (vs 2000 before)
        content = lead.content[:300]
        title = lead.title or ""
        full_text = f"{title}\n\n{content}" if title else content

        # Service filter (if applicable) - STRENGTHENED FOR STRICT FILTERING
        service_filter = ""
        if self.target_service:
            if self.target_service.upper() == 'RWA':
                service_filter = """**🚨 CRITICAL: ONLY QUALIFY RWA TOKENIZATION LEADS. REJECT ALL OTHER SERVICES.**

**REQUIRED RWA KEYWORDS (must have at least one):**
- "tokenize", "tokenization", "tokenizing"
- "RWA", "real world asset", "real-world asset"
- "fractional ownership", "fractionalize"
- "security token", "STO", "asset-backed token"

**REJECT IMMEDIATELY IF:**
- Crypto/Web3 development (unless specifically about asset tokenization)
- AI/ML services (not RWA)
- General blockchain development (unless tokenization-related)
- Smart contracts (unless for tokenization)
- DeFi projects (unless RWA-focused)
"""
            elif self.target_service.upper() == 'CRYPTO':
                service_filter = f"""**🚨 CRITICAL: ONLY QUALIFY CRYPTO/WEB3 LEADS. REJECT RWA/AI/OTHER SERVICES.**

**MUST ask for:** Crypto development, Web3 integration, DeFi, cryptocurrency
**REJECT:** RWA tokenization, AI/ML, general blockchain
"""
            elif 'AI' in self.target_service.upper() or 'ML' in self.target_service.upper():
                service_filter = f"""**🚨 CRITICAL: ONLY QUALIFY AI/ML LEADS. REJECT CRYPTO/RWA/BLOCKCHAIN.**

**MUST ask for:** AI automation, ML models, chatbots, AI integration
**REJECT:** Crypto, blockchain, tokenization
"""
            else:
                service_filter = f"🚨 CRITICAL: ONLY qualify {self.target_service} leads. REJECT all other services. "

        # Targeted search boost
        search_boost = ""
        if lead.source == 'reddit' and lead.metadata.get('targeted_search'):
            search_boost = f"🎯 High-intent search lead (phrase: '{lead.metadata.get('search_phrase', '')}'). +0.15 confidence if qualified. "

        # Build service-specific context
        if self.target_service == 'RWA' or (service_filter and 'RWA' in service_filter):
            service_context = """**CRITICAL: RWA-ONLY MODE - Reject ALL non-RWA leads**

**Shamla Tech RWA Services:**
- Real estate tokenization (commercial/residential property fractionalization)
- Asset tokenization platforms (art, commodities, securities)
- Security Token Offerings (STO) infrastructure
- Fractional ownership solutions
- Regulatory-compliant tokenization

**RWA QUALIFICATION - ACCEPT if ANY of these patterns:**

1. **EXPLICIT TOKENIZATION INTENT** (confidence: 0.8-1.0)
   - Direct mention: "tokenize", "tokenization", "tokenizing"
   - Asset + action: "tokenize my property", "fractionalize our real estate"
   - Platform seeking: "tokenization platform", "STO platform"

2. **IMPLICIT TOKENIZATION INTENT** (confidence: 0.6-0.8)
   - Fractional ownership + real assets (property, art, securities)
   - "Digital securities" + real assets
   - "Blockchain for real estate" + investment/fractionalization context
   - "Asset-backed tokens" or "security tokens"
   - Mentions STO, Reg D, 506c offerings (regulatory terms)

3. **EXPLORATORY/RESEARCH** (confidence: 0.5-0.7)
   - "Exploring/considering/researching" + tokenization/fractional ownership
   - Questions about tokenization: "how to tokenize", "best way to tokenize"
   - Asset owner researching solutions: "options for fractionalizing my property"

**AUTOMATIC REJECT:**
- AI/ML projects (no asset tokenization)
- Pure blockchain dev (no specific assets)
- Crypto payments/wallets (no real world assets)
- General smart contracts (not tokenization-focused)
- DeFi protocols (unless explicitly for RWA/asset tokenization)
- Job postings: [Hiring] employee positions
- Service providers: [For Hire] developers offering services
- News/discussion: "What do you think about tokenization?"

**EDGE CASES - USE CONTEXT:**
- "Hiring tokenization consultant" → ACCEPT (seeking vendor, not employee)
- "Blockchain solution for real estate fund" → ACCEPT if mentions fractionalization/investment
- "Digital platform for property investment" → ACCEPT if implies fractional ownership"""
            rejection_rule = "\n**MANDATORY: If not about ASSET TOKENIZATION (explicit OR implicit), set is_qualified=false with reason='Not RWA - [topic]' and service_match=[]"
        else:
            service_context = "**Services:** RWA Tokenization, Crypto/Web3, Blockchain, AI/ML"
            rejection_rule = ""

        prompt = f"""Qualify lead for Shamla Tech (India-based Web3/RWA firm). {service_filter}{search_boost}

**Lead:** {full_text}

{service_context}{rejection_rule}

**Qualify if ALL TRUE:**
1. ASSET EXISTS: Property, real estate, securities, art, commodities, financial instrument
2. TOKENIZATION INTENT: "tokenize", "fractional ownership", "STO", "asset-backed tokens"
3. BUYER ROLE: Asset owner/business seeking service (NOT job seeker, NOT service provider)

**Examples of QUALIFIED RWA leads:**
- "I own a commercial property and want to tokenize it for fractional ownership"
- "Looking for a platform to tokenize our art collection"
- "Need help with security token offering for our real estate fund"
- "How to tokenize commodities for our trading platform?"

**Examples of REJECTED (not RWA):**
- "[Hiring] Blockchain developer" → Job post
- "[For Hire] Smart contract developer" → Service provider
- "Need AI automation" → Wrong service (AI not RWA)
- "Building a DeFi protocol" → DeFi not asset tokenization
- "Cross-chain ZK proofs" → Blockchain tech not RWA

**Confidence:**
- 0.85-1.0: "Tokenize MY [specific asset]" with asset type named
- 0.7-0.85: "How to tokenize [asset type]" + business context
- 0.5-0.7: Implicit RWA need (fractional ownership + real asset mentioned)
- 0.0-0.5: Reject (no asset tokenization intent)

JSON: {{"is_qualified": true/false, "confidence_score": 0.0-1.0, "reason": "[ACCEPT: asset type + tokenization intent] OR [REJECT: not RWA - topic]", "service_match": ["RWA Tokenization"]}}"""

        return prompt
    
    def _validate_service_match(self, result: dict, lead: Lead) -> dict:
        """
        Validate that LLM-qualified lead actually matches target service.
        Overrides LLM decision if service mismatch detected.
        
        This is a CRITICAL VALIDATION LAYER that catches false positives from the LLM.
        
        Args:
            result: LLM qualification result
            lead: Original lead object
            
        Returns:
            dict: Modified result with corrected qualification if needed
        """
        if not self.target_service or not result.get('is_qualified'):
            return result
        
        service_match = result.get('service_match', [])
        
        # Check if target service is in the matched services
        if self.target_service.upper() == 'RWA':
            # For RWA, require "RWA", "tokenization", or "tokenize" in service match
            rwa_keywords = ['rwa', 'tokenization', 'tokenize', 'asset tokenization', 'real world']
            has_rwa = any(
                any(keyword in service.lower() for keyword in rwa_keywords)
                for service in service_match
            )
            
            if not has_rwa:
                # LLM qualified wrong service - override
                print(f"  🚫 VALIDATION OVERRIDE: LLM found {service_match} but filtering for RWA only")
                result['is_qualified'] = False
                result['confidence_score'] = 0.0
                result['reason'] = f"Service mismatch: LLM found {service_match} but filtering for RWA tokenization only"
                result['service_match'] = []
        
        elif self.target_service.upper() == 'CRYPTO':
            crypto_keywords = ['crypto', 'web3', 'defi', 'cryptocurrency', 'blockchain']
            has_crypto = any(
                any(keyword in service.lower() for keyword in crypto_keywords)
                for service in service_match
            )
            if not has_crypto:
                print(f"  🚫 VALIDATION OVERRIDE: LLM found {service_match} but filtering for Crypto only")
                result['is_qualified'] = False
                result['confidence_score'] = 0.0
                result['reason'] = f"Service mismatch: filtering for Crypto only"
                result['service_match'] = []
        
        elif 'AI' in self.target_service.upper() or 'ML' in self.target_service.upper():
            ai_keywords = ['ai', 'ml', 'machine learning', 'artificial intelligence', 'chatbot']
            has_ai = any(
                any(keyword in service.lower() for keyword in ai_keywords)
                for service in service_match
            )
            if not has_ai:
                print(f"  🚫 VALIDATION OVERRIDE: LLM found {service_match} but filtering for AI/ML only")
                result['is_qualified'] = False
                result['confidence_score'] = 0.0
                result['reason'] = f"Service mismatch: filtering for AI/ML only"
                result['service_match'] = []
        
        return result
    
    def _should_send_to_llm(self, lead: Lead) -> tuple[bool, str]:
        """
        CONSOLIDATED pre-filter. Single decisive check.

        Returns:
            tuple: (should_send: bool, reason: str)
                - True: MIGHT be inquiry → send to LLM
                - False: DEFINITELY not inquiry → skip LLM (with reason)
        """
        content = lead.content
        title = lead.title or ""
        full_text = f"{title} {content}".lower()

        # BLOCK 1: Obvious spam/self-promotion (multiple indicators required)
        spam_phrases = [
            "check out our", "proud to announce", "just launched",
            "join our", "register now", "click here", "buy now",
            "visit our website", "dm for more", "link in bio"
        ]
        spam_count = sum(1 for phrase in spam_phrases if phrase in full_text)
        if spam_count >= 2:
            return False, "spam/self-promotion (2+ indicators)"

        # BLOCK 2: Job postings (company hiring employees, NOT consultants/vendors)
        # Exception: Allow if seeking consultant/vendor/agency
        hiring_indicators = [
            "[hiring]", "we are hiring", "we're hiring", "apply now",
            "submit your resume", "send cv to", "years experience required",
            "remote work in the ai", "earn $", "weekly ai projects"
        ]
        
        if any(indicator in full_text for indicator in hiring_indicators):
            # EXCEPTION: Check if hiring consultant/vendor (legitimate service request)
            consultant_indicators = [
                "hiring consultant", "hiring agency", "hiring vendor",
                "hiring freelancer", "hiring contractor", "seeking consultant",
                "looking for consultant", "need consultant", "consultant needed",
                "agency needed", "vendor needed", "freelancer needed"
            ]
            
            # If hiring consultant/vendor, allow through (not employee hiring)
            if any(consultant in full_text for consultant in consultant_indicators):
                pass  # Allow - this is a service request
            else:
                return False, "job posting (company hiring employees)"
        
        # BLOCK 3: Service providers offering services (not seeking)
        # These are freelancers/agencies promoting themselves
        offering_indicators = [
            "[for hire]", "i offer", "my services include",
            "i can help with", "i specialize in", "my expertise",
            "portfolio:", "dm me for", "contact me at"
        ]
        if any(indicator in full_text for indicator in offering_indicators):
            return False, "service provider (offering services)"

        # ALLOW: Everything else goes to LLM
        # Let LLM decide on borderline cases instead of aggressive pre-filtering
        return True, ""
    
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
            
            # 🔍 CRITICAL: Validate service match using robust validation method
            if self.target_service and result["is_qualified"]:
                result = self._validate_service_match(result, lead)
            
            return result
            
        except json.JSONDecodeError as e:
            # Include the actual response text in error for debugging
            raw_response = response.text if 'response' in locals() else "No response"
            raise Exception(f"Gemini JSON parse error: {str(e)}. Raw response: {raw_response[:500]}")
        except Exception as e:
            raise Exception(f"Gemini API call failed: {str(e)}")
    
    def qualify_leads_batch_llm(self, leads: list[Lead], batch_size: int = 10) -> list[dict]:
        """
        IMPROVED: Send multiple leads to LLM in a single API call for batch processing.

        Benefits over individual qualification:
        - Comparative analysis: LLM can compare leads side-by-side
        - Consistency: More consistent scoring across similar leads
        - Cost efficient: Fewer API calls (1 call for N leads vs N calls)
        - Pattern recognition: LLM sees patterns across leads

        Args:
            leads: List of leads to qualify (max 10 per batch recommended)
            batch_size: Max leads per API call (default: 10)

        Returns:
            List of qualification dicts in same order as input leads
        """
        all_results = []

        # Process in batches of batch_size
        for i in range(0, len(leads), batch_size):
            batch_leads_raw = leads[i:i+batch_size]
            
            # 🔍 CRITICAL: Apply pre-filter to remove obvious non-inquiries
            batch_leads = []
            for lead in batch_leads_raw:
                should_send, block_reason = self._should_send_to_llm(lead)
                if should_send:
                    batch_leads.append(lead)
                else:
                    # Add pre-filtered result
                    all_results.append({
                        "is_qualified": False,
                        "confidence_score": 0.0,
                        "reason": f"Pre-filter blocked: {block_reason}",
                        "service_match": [],
                        "skipped_llm": True,
                        "llm_provider": "none"
                    })
            
            # Skip batch if all leads were pre-filtered
            if not batch_leads:
                continue

            # Build batch prompt
            batch_prompt = self._build_batch_qualification_prompt(batch_leads)

            try:
                # Call OpenAI API with batch
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a strict sales lead qualifier analyzing multiple leads. Qualify each lead independently but maintain consistency. Respond with valid JSON only."
                        },
                        {
                            "role": "user",
                            "content": batch_prompt
                        }
                    ],
                    temperature=0.2,
                    max_tokens=2000,  # More tokens for multiple leads
                    response_format={"type": "json_object"}
                )

                # Parse batch results
                result_text = response.choices[0].message.content.strip()

                # Remove markdown if present
                if result_text.startswith("```json"):
                    result_text = result_text[7:]
                if result_text.startswith("```"):
                    result_text = result_text[3:]
                if result_text.endswith("```"):
                    result_text = result_text[:-3]
                result_text = result_text.strip()

                batch_results = json.loads(result_text)

                # Validate structure (should be array of results)
                if isinstance(batch_results, dict) and 'results' in batch_results:
                    batch_results = batch_results['results']

                if not isinstance(batch_results, list):
                    raise ValueError(f"Expected list of results, got {type(batch_results)}")

                # Ensure we have result for each lead
                if len(batch_results) != len(batch_leads):
                    print(f"⚠️ Warning: Expected {len(batch_leads)} results, got {len(batch_results)}")
                    # Pad with error results if needed
                    while len(batch_results) < len(batch_leads):
                        batch_results.append({
                            "is_qualified": False,
                            "confidence_score": 0.0,
                            "reason": "Missing result from LLM batch response",
                            "service_match": [],
                            "error": "Batch response incomplete"
                        })

                # Add LLM provider marker and apply robust service validation
                for idx, result in enumerate(batch_results):
                    result['llm_provider'] = 'openai'
                    
                    # 🔍 CRITICAL: Apply robust service validation
                    if self.target_service and result.get("is_qualified"):
                        # Get corresponding lead from batch
                        if idx < len(batch_leads):
                            lead_num = i + idx + 1  # i is the batch offset
                            print(f"  🔍 [Lead #{lead_num}] Service filter: {self.target_service}, LLM matched: {result.get('service_match', [])}")
                            result = self._validate_service_match(result, batch_leads[idx])
                            if result["is_qualified"]:
                                print(f"  ✅ [Lead #{lead_num}] Validation PASSED")
                            else:
                                print(f"  ❌ [Lead #{lead_num}] Validation FAILED - rejected")
                            # Update the result in the list
                            batch_results[idx] = result

                all_results.extend(batch_results)

            except OpenAIError as e:
                # Fallback to individual qualification on error
                print(f"⚠️ Batch LLM call failed ({str(e)[:50]}...), falling back to individual qualification...")
                for lead in batch_leads:
                    individual_result = self.qualify_lead(lead)
                    all_results.append(individual_result)

            except json.JSONDecodeError as e:
                print(f"⚠️ Failed to parse batch LLM response: {e}")
                # Fallback to individual
                for lead in batch_leads:
                    all_results.append(self.qualify_lead(lead))

            except Exception as e:
                print(f"⚠️ Unexpected error in batch LLM: {e}")
                for lead in batch_leads:
                    all_results.append(self.qualify_lead(lead))

        return all_results

    def _build_batch_qualification_prompt(self, leads: list[Lead]) -> str:
        """Build lean batch prompt - 300 chars per lead max."""

        # Build lead summaries (OPTIMIZED: 300 chars per lead)
        lead_summaries = []
        for idx, lead in enumerate(leads, 1):
            content = lead.content[:300]  # Simple truncation
            title = lead.title or ""
            full_text = f"{title}\n{content}" if title else content

            lead_summary = f"Lead #{idx}: {full_text}"
            lead_summaries.append(lead_summary)

        all_leads_text = "\n\n".join(lead_summaries)

        prompt = f"""Qualify {len(leads)} leads for Shamla Tech (Web3/RWA/Blockchain/AI).

**Services:** RWA Tokenization, Crypto/Web3, Blockchain, AI/ML

**Qualify if:** (1) Explicit help-seeking, (2) Buying signals (budget/timeline/urgency), (3) Implicit (problem + context)
**Reject:** Discussion, news, spam, no business context

**Leads:**
{all_leads_text}

JSON array: {{"results": [{{"lead_number": 1, "is_qualified": true/false, "confidence_score": 0.0-1.0, "reason": "quoted phrase", "service_match": ["RWA Tokenization"]}}]}}

Return exactly {len(leads)} results in order."""

        return prompt

    def qualify_lead(self, lead: Lead) -> dict:
        """
        Qualify a lead using consolidated pre-filter + GPT-4-turbo.

        OPTIMIZED: Single decisive pre-filter that only blocks obvious spam/hiring.

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
        # CONSOLIDATED PRE-FILTER: Single decisive check
        should_send, block_reason = self._should_send_to_llm(lead)

        if not should_send:
            return {
                "is_qualified": False,
                "confidence_score": 0.0,
                "reason": f"Pre-filter blocked: {block_reason}",
                "service_match": [],
                "skipped_llm": True
            }

        # If pre-filter passes, proceed with LLM call
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
            
            # 🔍 CRITICAL: Validate service match - catches false positives
            # This robust validation layer overrides LLM if service mismatch detected
            if self.target_service and result["is_qualified"]:
                print(f"  🔍 Service filter active: {self.target_service}")
                print(f"  📋 LLM matched services: {result.get('service_match', [])}")
                result = self._validate_service_match(result, lead)
                if result["is_qualified"]:
                    print(f"  ✅ Service validation PASSED")
                else:
                    print(f"  ❌ Service validation FAILED - lead rejected")
            
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

    async def qualify_leads_in_batches(
        self,
        leads: list[Lead],
        batch_size: int = 100,
        max_concurrent: int = 5,
        llm_batch_size: int = 20,
        progress_callback: Optional[callable] = None
    ) -> list[dict]:
        """
        OPTIMIZED: Qualify leads in batches with progressive saving, cost tracking, AND LLM-side batching.

        Benefits:
        - Checkpointing: Save after each batch (crash recovery)
        - Progress visibility: See results incrementally
        - Cost tracking: Monitor API spend per batch
        - Memory efficient: Process in chunks
        - LLM batching: Send multiple leads per API call for better consistency

        Args:
            leads: List of Lead objects
            batch_size: Leads per progress batch (default: 100, increased from 50)
            max_concurrent: Max concurrent API requests within batch
            llm_batch_size: Leads per LLM API call (default: 20, increased from 10) - HIGHER = BETTER CONSISTENCY
            progress_callback: Optional function called after each batch

        Returns:
            List of qualification results (same format as qualify_leads_concurrent)
        """
        total_leads = len(leads)
        num_batches = (total_leads + batch_size - 1) // batch_size  # Ceiling division

        print(f"\n🤖 Starting batch qualification with LLM-side batching:")
        print(f"   Total leads: {total_leads}")
        print(f"   Progress batch size: {batch_size}")
        print(f"   LLM batch size: {llm_batch_size} leads/API call (better consistency!)")
        print(f"   Number of progress batches: {num_batches}")

        all_results = []
        total_qualified = 0
        total_llm_calls = 0
        estimated_cost = 0.0

        for batch_num in range(num_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, total_leads)
            batch_leads = leads[start_idx:end_idx]

            print(f"\n{'='*60}")
            print(f"📦 Progress Batch {batch_num + 1}/{num_batches} ({len(batch_leads)} leads)")
            print(f"{'='*60}")

            # IMPROVED: Use LLM-side batch processing
            batch_results = await asyncio.to_thread(
                self.qualify_leads_batch_llm,
                batch_leads,
                llm_batch_size
            )

            # Track statistics (LLM-side batching changes the calculation)
            batch_qualified = sum(1 for r in batch_results if r.get("is_qualified", False))
            # Calculate actual API calls made (with LLM batching, it's leads/llm_batch_size)
            num_api_calls = (len(batch_leads) + llm_batch_size - 1) // llm_batch_size
            batch_llm_calls = num_api_calls
            # Cost is higher per call with batching but total cost is lower
            batch_cost = batch_llm_calls * (0.003 * llm_batch_size * 0.3)  # ~30% of individual cost

            total_qualified += batch_qualified
            total_llm_calls += batch_llm_calls
            estimated_cost += batch_cost

            # Batch summary
            print(f"\n   Batch {batch_num + 1} Results:")
            print(f"   ✅ Qualified: {batch_qualified}/{len(batch_leads)} ({batch_qualified/len(batch_leads)*100:.1f}%)")
            print(f"   💰 LLM API calls: {batch_llm_calls} (batched {len(batch_leads)} leads into {batch_llm_calls} calls)")
            print(f"   💵 Est. cost: ${batch_cost:.3f} (vs ${len(batch_leads)*0.003:.3f} individual)")
            print(f"   📊 Running total: {total_qualified}/{end_idx} qualified ({total_qualified/end_idx*100:.1f}%)")

            all_results.extend(batch_results)

            # Call progress callback if provided
            if progress_callback:
                progress_callback(batch_num + 1, num_batches, batch_results, {
                    'batch_qualified': batch_qualified,
                    'batch_llm_calls': batch_llm_calls,
                    'batch_cost': batch_cost,
                    'total_qualified': total_qualified,
                    'total_processed': end_idx,
                    'estimated_total_cost': estimated_cost
                })

        # Final summary
        print(f"\n{'='*60}")
        print(f"✅ BATCH QUALIFICATION COMPLETE")
        print(f"{'='*60}")
        print(f"   Total leads processed: {total_leads}")
        print(f"   Total qualified: {total_qualified} ({total_qualified/total_leads*100:.1f}%)")
        print(f"   Total LLM calls: {total_llm_calls}")
        print(f"   💰 Estimated total cost: ${estimated_cost:.2f}")
        print(f"{'='*60}\n")

        return all_results


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


async def qualify_leads_in_batches(
    leads: list[Lead],
    batch_size: int = 100,
    max_concurrent: int = 5,
    llm_batch_size: int = 20,
    target_service: Optional[str] = None,
    progress_callback: Optional[callable] = None
) -> list[dict]:
    """
    OPTIMIZED: Qualify leads in batches with progressive saving, cost tracking, AND LLM-side batching.

    Benefits over qualify_leads_concurrent:
    - LLM batching: Send multiple leads per API call (better consistency, lower cost)
    - Checkpointing: Save results after each batch (crash recovery)
    - Progress visibility: See results incrementally
    - Cost tracking: Monitor API spend per batch
    - Memory efficient: Process in manageable chunks

    Args:
        leads: List of Lead objects
        batch_size: Leads per progress batch (default: 100, increased from 50)
        max_concurrent: Max concurrent API requests (deprecated with LLM batching)
        llm_batch_size: Leads per LLM API call (default: 20, increased from 10) - HIGHER = BETTER CONSISTENCY
        target_service: Filter for specific service (e.g., 'RWA', 'Crypto')
        progress_callback: Optional callback function(batch_num, total_batches, batch_results, stats)

    Returns:
        List of qualification results in same order as input leads

    Example:
        # Basic usage with LLM batching (OPTIMIZED DEFAULTS)
        results = await qualify_leads_in_batches(
            leads,
            batch_size=100,    # Process 100 leads per checkpoint
            llm_batch_size=20  # 20 leads per API call (better consistency!)
        )

        # Higher LLM batch size = even more consistent results
        results = await qualify_leads_in_batches(
            leads,
            llm_batch_size=25  # Maximum consistency
        )

        # With progress callback for saving
        def save_batch(batch_num, total_batches, batch_results, stats):
            print(f"Batch {batch_num}: {stats['batch_qualified']} qualified")
            # Save to Excel/JSON here

        results = await qualify_leads_in_batches(
            leads,
            batch_size=100,
            llm_batch_size=20,
            progress_callback=save_batch
        )
    """
    qualifier = LLMLeadQualifier(target_service=target_service)
    return await qualifier.qualify_leads_in_batches(
        leads,
        batch_size=batch_size,
        max_concurrent=max_concurrent,
        llm_batch_size=llm_batch_size,
        progress_callback=progress_callback
    )
