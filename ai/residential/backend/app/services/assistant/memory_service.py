"""Customer Persistent Memory Service for GridVision Residential Assistant.

Handles memory extraction, validation, correction, deletion, and relevance-scoped retrieval.
Guarantees strict customer data isolation.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.infrastructure.repositories.conversation_memory_repository import (
    ConversationMemoryRepository,
)
from app.services.assistant.memory_contracts import (
    CustomerMemoryItem,
    MemoryCategory,
)

logger = logging.getLogger("gridvision.services.assistant.memory")


class CustomerMemoryService:
    """Manages persistent facts, preferences, and verified customer premises data."""

    def __init__(self, repository: Optional[ConversationMemoryRepository] = None) -> None:
        self.repository = repository or ConversationMemoryRepository()

    # -------------------------------------------------------------------------
    # Memory Retrieval & Relevance Filtering
    # -------------------------------------------------------------------------

    def get_all_memories(self, user_id: str, persona: str = "residential") -> List[CustomerMemoryItem]:
        """Retrieve all active memories belonging to the authenticated user."""
        return self.repository.get_memories(user_id=user_id, persona=persona, active_only=True)

    def select_relevant_memories(
        self,
        user_id: str,
        query: str,
        persona: str = "residential",
        active_workflow: Optional[str] = None,
        max_memories: int = 5,
    ) -> List[CustomerMemoryItem]:
        """Select a focused subset of memories strictly relevant to the current user query.
        
        Prevents carrying irrelevant historical facts into unrelated domain queries.
        """
        all_mems = self.get_all_memories(user_id=user_id, persona=persona)
        if not all_mems:
            return []

        q_low = query.lower()

        # Domain keywords mapping
        is_planning = active_workflow == "house_planning" or any(w in q_low for w in [
            "house plan", "new house", "wiring", "electrical layout", "connected load",
            "peak demand", "sub-circuit", "bedroom", "built-up", "square meter", "sqm", "sq ft"
        ])
        is_appliance = active_workflow == "appliance_lifecycle" or any(w in q_low for w in [
            "ac", "air condition", "air conditioner", "inverter", "fan", "bldc", "refrigerator",
            "geyser", "appliance", "star rating", "iseer", "payback", "upgrade", "replace"
        ])
        is_cost = active_workflow == "cost_management" or any(w in q_low for w in [
            "save", "lower bill", "reduce bill", "cost management", "saving", "tariff", "peak hours"
        ])
        is_telemetry = any(w in q_low for w in [
            "usage", "consumption", "kwh", "historical", "bill", "yesterday", "last month", "predict"
        ])

        relevant: List[CustomerMemoryItem] = []

        for m in all_mems:
            k = m.key.lower()
            cat = m.category.lower()

            match = False
            # 1. Property facts: relevant to house planning and general household context
            if k in ("property_type", "location_city", "built_up_area_m2", "floors_count", "bedrooms_count", "occupancy_count"):
                if is_planning or any(term in q_low for term in ["my house", "my home", "my property", "city", "bedroom", "area"]):
                    match = True

            # 2. Appliance ownership & preferences: relevant to appliance queries and planning
            elif k in ("owned_ac_count", "owned_appliances", "preferred_star_rating", "ac_type", "fans_count", "has_solar_pv", "has_ev"):
                if is_appliance or is_planning or any(term in q_low for term in ["my ac", "my fan", "my appliances", "solar", "ev"]):
                    match = True

            # 3. Energy priorities & constraints: relevant to cost management & recommendations
            elif cat in ("priority", "constraint", "preference") or k in ("target_savings_pct", "efficiency_priority", "response_style"):
                if is_cost or is_planning or is_appliance or any(term in q_low for term in ["priority", "save", "budget", "target"]):
                    match = True

            # 4. Explicit direct keyword match in query
            elif k in q_low or str(m.value).lower() in q_low:
                match = True

            if match and m not in relevant:
                relevant.append(m)

        return relevant[:max_memories]

    # -------------------------------------------------------------------------
    # Memory Extraction & Processing
    # -------------------------------------------------------------------------

    def extract_and_persist_candidate_memories(
        self,
        user_id: str,
        user_prompt: str,
        conversation_id: Optional[str] = None,
        persona: str = "residential",
    ) -> List[CustomerMemoryItem]:
        """Extract confirmed factual assertions from user text and persist them with provenance."""
        clean_user = str(user_id).strip()
        p = user_prompt.strip()
        p_low = p.lower()
        extracted: List[CustomerMemoryItem] = []

        # 0. Check for explicit customer deletion requests
        if any(w in p_low for w in ["forget my", "delete my preference", "remove my preference", "delete memory", "clear my saved"]):
            if "preference" in p_low or "efficiency" in p_low:
                self.repository.delete_memory(clean_user, "efficiency_priority")
                self.repository.delete_memory(clean_user, "preferred_star_rating")
            if "solar" in p_low:
                self.repository.delete_memory(clean_user, "has_solar_pv")
            if "ac" in p_low:
                self.repository.delete_memory(clean_user, "owned_ac_count")
            return []

        # 1. Location / City extraction
        # Examples: "I live in Bengaluru", "my house is in Bangalore", "located in Mumbai", "city: Delhi"
        city_match = re.search(r"\b(?:in|city|location|at)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\b", p)
        if city_match:
            candidate_city = city_match.group(1).strip()
            known_cities = {
                "bangalore", "bengaluru", "mumbai", "delhi", "new delhi", "chennai",
                "hyderabad", "pune", "kolkata", "ahmedabad", "jaipur", "kochi",
            }
            if candidate_city.lower() in known_cities:
                normalized_city = "Bengaluru" if candidate_city.lower() in ("bangalore", "bengaluru") else candidate_city.title()
                item = CustomerMemoryItem(
                    user_id=clean_user,
                    persona=persona,
                    category=MemoryCategory.PROPERTY.value,
                    key="location_city",
                    value=normalized_city,
                    source_conversation_id=conversation_id,
                    source_message=p[:200],
                    confidence=1.0,
                )
                self.repository.save_or_update_memory(clean_user, item)
                extracted.append(item)

        # 2. Bedrooms count extraction
        # Examples: "I have 3 bedrooms", "my 3bhk apartment", "3 bedroom house", "we have 2 bedrooms"
        bhk_match = re.search(r"\b(\d+)\s*(?:bhk|bedrooms?|bed\s*rooms?)\b", p_low)
        if bhk_match:
            num_beds = int(bhk_match.group(1))
            if 1 <= num_beds <= 10:
                item = CustomerMemoryItem(
                    user_id=clean_user,
                    persona=persona,
                    category=MemoryCategory.PROPERTY.value,
                    key="bedrooms_count",
                    value=num_beds,
                    source_conversation_id=conversation_id,
                    source_message=p[:200],
                    confidence=1.0,
                )
                self.repository.save_or_update_memory(clean_user, item)
                extracted.append(item)

        # 3. Property Type extraction
        # Examples: "independent house", "bungalow", "apartment", "villa", "row house"
        if "independent house" in p_low or "bungalow" in p_low:
            prop_type = "independent_house"
        elif "apartment" in p_low or "flat" in p_low:
            prop_type = "apartment"
        elif "villa" in p_low:
            prop_type = "villa"
        elif "row house" in p_low:
            prop_type = "row_house"
        else:
            prop_type = None

        if prop_type:
            item = CustomerMemoryItem(
                user_id=clean_user,
                persona=persona,
                category=MemoryCategory.PROPERTY.value,
                key="property_type",
                value=prop_type,
                source_conversation_id=conversation_id,
                source_message=p[:200],
                confidence=1.0,
            )
            self.repository.save_or_update_memory(clean_user, item)
            extracted.append(item)

        # 4. Built-up area extraction
        # Examples: "1500 sq ft", "140 sqm", "140 sq.m", "150 m2"
        area_m2_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:sqm|sq\.m|m2|square\s*meters?)\b", p_low)
        area_sqft_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:sqft|sq\.ft|square\s*feet)\b", p_low)
        if area_m2_match:
            area = float(area_m2_match.group(1))
            if 20.0 <= area <= 2000.0:
                item = CustomerMemoryItem(
                    user_id=clean_user,
                    persona=persona,
                    category=MemoryCategory.PROPERTY.value,
                    key="built_up_area_m2",
                    value=round(area, 1),
                    source_conversation_id=conversation_id,
                    source_message=p[:200],
                    confidence=1.0,
                )
                self.repository.save_or_update_memory(clean_user, item)
                extracted.append(item)
        elif area_sqft_match:
            sqft = float(area_sqft_match.group(1))
            area_m2 = sqft / 10.764
            if 20.0 <= area_m2 <= 2000.0:
                item = CustomerMemoryItem(
                    user_id=clean_user,
                    persona=persona,
                    category=MemoryCategory.PROPERTY.value,
                    key="built_up_area_m2",
                    value=round(area_m2, 1),
                    source_conversation_id=conversation_id,
                    source_message=p[:200],
                    confidence=1.0,
                )
                self.repository.save_or_update_memory(clean_user, item)
                extracted.append(item)

        # 5. Appliance Ownership extraction & corrections
        # Examples: "I have 2 ACs", "I own 3 split ACs", "I said two ACs, not three"
        correction_ac_match = re.search(r"\b(?:said|mean|have|own)\s+(\w+|\d+)\s*(?:acs?|air\s*conditioners?)(?:,\s*not\s+(\w+|\d+))?", p_low)
        word_to_num = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
        if correction_ac_match:
            val_str = correction_ac_match.group(1)
            num_acs = word_to_num.get(val_str) or (int(val_str) if val_str.isdigit() else None)
            if num_acs is not None and 0 <= num_acs <= 15:
                item = CustomerMemoryItem(
                    user_id=clean_user,
                    persona=persona,
                    category=MemoryCategory.APPLIANCE.value,
                    key="owned_ac_count",
                    value=num_acs,
                    source_conversation_id=conversation_id,
                    source_message=p[:200],
                    confidence=1.0,
                )
                self.repository.save_or_update_memory(clean_user, item)
                extracted.append(item)

        # 6. Efficiency & Star Rating Preferences
        # Examples: "I prefer 5-star appliances", "only 5 star BEE", "high efficiency priority"
        if "5-star" in p_low or "5 star" in p_low:
            item = CustomerMemoryItem(
                user_id=clean_user,
                persona=persona,
                category=MemoryCategory.PREFERENCE.value,
                key="preferred_star_rating",
                value="5-Star",
                source_conversation_id=conversation_id,
                source_message=p[:200],
                confidence=1.0,
            )
            self.repository.save_or_update_memory(clean_user, item)
            extracted.append(item)

        if "high efficiency" in p_low or "maximum savings" in p_low:
            item = CustomerMemoryItem(
                user_id=clean_user,
                persona=persona,
                category=MemoryCategory.PRIORITY.value,
                key="efficiency_priority",
                value="high_efficiency",
                source_conversation_id=conversation_id,
                source_message=p[:200],
                confidence=1.0,
            )
            self.repository.save_or_update_memory(clean_user, item)
            extracted.append(item)

        return extracted

    def handle_customer_correction(
        self,
        user_id: str,
        correction_text: str,
        conversation_id: Optional[str] = None,
    ) -> Optional[CustomerMemoryItem]:
        """Detect and apply explicit user corrections (e.g. 'I said two ACs, not three')."""
        clean_user = str(user_id).strip()
        p = correction_text.strip().lower()

        # Check for AC correction
        if "ac" in p:
            match = re.search(r"\b(?:said|have|got|need|want|use)\s+(\d+|two|three|one|four|five)\s*(?:acs?|air\s*conditioners?)", p)
            word_to_num = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
            if match:
                raw_n = match.group(1)
                num = word_to_num.get(raw_n) or (int(raw_n) if raw_n.isdigit() else None)
                if num is not None:
                    item = CustomerMemoryItem(
                        user_id=clean_user,
                        persona="residential",
                        category=MemoryCategory.APPLIANCE.value,
                        key="owned_ac_count",
                        value=num,
                        source_conversation_id=conversation_id,
                        source_message=correction_text[:200],
                        confidence=1.0,
                    )
                    return self.repository.save_or_update_memory(clean_user, item)

        # Check for bedrooms correction
        if "bedroom" in p or "bhk" in p:
            match = re.search(r"\b(\d+|two|three|one|four|five)\s*(?:bedrooms?|bhk)", p)
            word_to_num = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
            if match:
                raw_n = match.group(1)
                num = word_to_num.get(raw_n) or (int(raw_n) if raw_n.isdigit() else None)
                if num is not None:
                    item = CustomerMemoryItem(
                        user_id=clean_user,
                        persona="residential",
                        category=MemoryCategory.PROPERTY.value,
                        key="bedrooms_count",
                        value=num,
                        source_conversation_id=conversation_id,
                        source_message=correction_text[:200],
                        confidence=1.0,
                    )
                    return self.repository.save_or_update_memory(clean_user, item)

        return None

    def process_user_deletions(
        self,
        user_id: str,
        user_message: str,
    ) -> List[str]:
        """Detect and process user requests to forget or clear stored preferences/memories."""
        clean_user = str(user_id).strip()
        msg_low = user_message.lower()
        deleted_keys: List[str] = []

        if any(w in msg_low for w in ["forget", "delete", "clear", "remove", "erase"]):
            # Check for solar budget or solar preferences
            if "solar" in msg_low:
                if self.repository.delete_memory(clean_user, "solar_budget_inr"):
                    deleted_keys.append("solar_budget_inr")
                if self.repository.delete_memory(clean_user, "has_solar_pv"):
                    deleted_keys.append("has_solar_pv")
            if "preference" in msg_low or "priority" in msg_low or "efficiency" in msg_low:
                if self.repository.delete_memory(clean_user, "efficiency_priority"):
                    deleted_keys.append("efficiency_priority")
                if self.repository.delete_memory(clean_user, "preferred_star_rating"):
                    deleted_keys.append("preferred_star_rating")
            if "ac" in msg_low or "cooling" in msg_low:
                if self.repository.delete_memory(clean_user, "owned_ac_count"):
                    deleted_keys.append("owned_ac_count")
            if "temperature" in msg_low or "thermostat" in msg_low or "setpoint" in msg_low:
                if self.repository.delete_memory(clean_user, "thermostat_setpoint"):
                    deleted_keys.append("thermostat_setpoint")

            # Also check if any active memory key is explicitly mentioned
            all_mems = self.get_all_memories(clean_user)
            for m in all_mems:
                if m.key.lower() in msg_low or m.key.replace("_", " ").lower() in msg_low:
                    if self.repository.delete_memory(clean_user, m.key):
                        if m.key not in deleted_keys:
                            deleted_keys.append(m.key)

        return deleted_keys

    def process_user_turn_for_memories(
        self,
        user_id: str,
        user_message: str,
        conversation_id: Optional[str] = None,
        persona: str = "residential",
    ) -> List[CustomerMemoryItem]:
        """Convenience turn processor: handles deletions, corrections, and extractions."""
        clean_user = str(user_id).strip()
        msg_low = user_message.lower()

        # Check for corrections first
        if any(w in msg_low for w in ["said", "not", "actually", "i mean", "correction"]):
            corr = self.handle_customer_correction(clean_user, user_message, conversation_id)
            if corr:
                return [corr]

        # Check for extractions
        return self.extract_and_persist_candidate_memories(clean_user, user_message, conversation_id, persona)

