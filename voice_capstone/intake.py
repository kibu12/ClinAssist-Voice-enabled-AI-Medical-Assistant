"""
Intake state machine for ClinAssist
Manages conversation flow: GREETING → COLLECTING → CLARIFYING → SUMMARIZING → COMPLETE
"""
from typing import Dict, Any, Optional, List
import re
from config import STATES, FIELD_PRIORITY
from memory import SessionMemory
from database import save_turn, update_session_state, get_session_state, update_symptom_record
import llm
import risk


def process_interaction(session_id: str, user_input: str) -> Dict[str, Any]:
    """
    Process user interaction through the intake state machine
    
    Args:
        session_id: Current session ID
        user_input: User's text input
    
    Returns:
        Dictionary with response_text, state, is_complete, and optional risk_assessment
    """
    # Load session memory
    memory = SessionMemory(session_id)
    current_state = get_session_state(session_id)
    
    # Save user input
    if user_input and user_input.strip():
        save_turn(session_id, "user", user_input)
    
    response_text = ""
    risk_assessment = None
    wellness_tip = None

    def _extract_severity_value(text: str) -> Optional[int]:
        if not text:
            return None

        lowered = text.lower()
        word_to_num = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10
        }

        range_match = re.search(r"\b(10|[1-9])\s*(?:to|-|–)\s*(10|[1-9])\b", lowered)
        if range_match:
            left = int(range_match.group(1))
            right = int(range_match.group(2))
            return max(1, min(10, round((left + right) / 2)))

        word_range_match = re.search(
            r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:to|-|–)\s*"
            r"(one|two|three|four|five|six|seven|eight|nine|ten)\b",
            lowered,
        )
        if word_range_match:
            left = word_to_num[word_range_match.group(1)]
            right = word_to_num[word_range_match.group(2)]
            return max(1, min(10, round((left + right) / 2)))

        single_num = re.search(r"\b(10|[1-9])\b", lowered)
        if single_num:
            return int(single_num.group(1))

        for word, value in word_to_num.items():
            if re.search(rf"\b{word}\b", lowered):
                return value

        return None

    def _extract_associated_symptoms(text: str) -> Optional[List[str]]:
        if not text:
            return None

        lowered = text.lower()

        negative_markers = [
            "no other symptoms",
            "no additional symptoms",
            "no more symptoms",
            "none",
            "nothing else",
            "just fever",
            "only fever",
        ]
        if any(marker in lowered for marker in negative_markers):
            return ["none reported"]

        symptom_aliases = [
            ("chills", ["chill", "chills"]),
            ("body aches", ["body ache", "body aches", "aches", "achy"]),
            ("headache", ["headache", "head pain"]),
            ("fatigue", ["fatigue", "tired", "weak"]),
            ("sweating", ["sweating", "sweats"]),
            ("cough", ["cough"]),
            ("sore throat", ["sore throat", "throat pain"]),
            ("runny nose", ["runny nose", "congestion"]),
            ("nausea", ["nausea", "nauseous"]),
            ("vomiting", ["vomit", "vomiting"]),
            ("diarrhea", ["diarrhea", "loose stools"]),
            ("dizziness", ["dizzy", "dizziness"]),
            ("shortness of breath", ["shortness of breath", "breathless"]),
        ]

        found: List[str] = []
        for canonical, aliases in symptom_aliases:
            if any(alias in lowered for alias in aliases):
                found.append(canonical)

        if not found:
            return None

        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for symptom in found:
            if symptom not in seen:
                deduped.append(symptom)
                seen.add(symptom)

        return deduped

    def _finalize_intake(symptom_data: Dict[str, Any], partial: bool = False):
        nonlocal risk_assessment, response_text, wellness_tip

        update_session_state(session_id, STATES["SUMMARIZING"])

        # Categorize risk (deterministic)
        risk_result = risk.categorize_risk(symptom_data)
        risk_assessment = risk_result

        # Save risk assessment
        update_symptom_record(session_id, {
            "risk_level": risk_result["risk_level"],
            "risk_reason": risk_result["reason"],
            "recommended_action": risk_result["recommended_action"]
        })

        # Generate and save summary
        summary = llm.generate_summary(symptom_data, session_id)
        update_symptom_record(session_id, {"summary": summary})

        # ALWAYS get a tip/recommendation for the separate UI block
        if risk_result['risk_level'] in ["LOW", "MODERATE"]:
            wellness_tip = llm.generate_health_advice(symptom_data, session_id)
        else:
            # For HIGH/CRITICAL, give a strong warning tip
            wellness_tip = f"Please prioritize seeking medical evaluation as advised. {risk_result['recommended_action']}"

        # Move straight to complete
        response_text = "I've completed your symptom check based on the details provided. Your clinical summary is now ready."
        update_session_state(session_id, STATES["COMPLETE"])
    
    # State machine logic
    if current_state == STATES["GREETING"]:
        # Welcome and ask for chief complaint
        response_text = (
            "Hi, I'm ClinAssist. I'll ask a few simple questions about how you feel. "
            "What problem are you having today?"
        )
        update_session_state(session_id, STATES["COLLECTING"])
    
    elif current_state == STATES["COLLECTING"] or current_state == STATES["CLARIFYING"]:
        user_lower = (user_input or "").lower()

        # Immediate stop for explicit severe wording
        if re.search(r"\bsevere\b", user_lower):
            risk_result = {
                "risk_level": "CRITICAL",
                "reason": "User reported severe symptoms, which requires immediate medical escalation.",
                "recommended_action": "Seek doctor care immediately. If symptoms are worsening or dangerous, go to emergency care now."
            }
            risk_assessment = risk_result

            existing_data = memory.get_symptom_data()
            chief_complaint = existing_data.get("chief_complaint") or (user_input or "")
            severe_summary = (
                f"Chief Complaint: {chief_complaint}\n"
                f"Duration: {existing_data.get('duration') or 'Not reported'}\n"
                f"Severity (1-10): {existing_data.get('severity') or 'Not reported'}\n"
                f"Progression: {existing_data.get('progression') or 'Not reported'}\n"
                f"Affected Body Part: {existing_data.get('affected_body_part') or 'Not reported'}\n"
                f"Onset Type: {existing_data.get('onset_type') or 'Not reported'}\n"
                f"Associated Symptoms: {existing_data.get('associated_symptoms') or 'Not reported'}\n"
                "Clinical Note: Intake stopped because user reported severe symptoms."
            )

            update_symptom_record(session_id, {
                "chief_complaint": chief_complaint,
                "risk_level": risk_result["risk_level"],
                "risk_reason": risk_result["reason"],
                "recommended_action": risk_result["recommended_action"],
                "summary": severe_summary,
            })

            response_text = (
                "This sounds severe, so I am marking this as critical and ending this intake now. "
                "Please seek doctor care immediately."
            )
            wellness_tip = "Critical: seek doctor care immediately."
            update_session_state(session_id, STATES["COMPLETE"])

        # Immediate stop for urgent keywords: do not continue seven-question intake
        urgent_detected = risk.detect_urgent_keyword(user_input or "")
        if (not response_text) and urgent_detected:
            risk_result = risk.build_urgent_assessment(urgent_detected, user_input or "")
            risk_assessment = risk_result

            existing_data = memory.get_symptom_data()
            chief_complaint = existing_data.get("chief_complaint") or (user_input or "")
            urgent_summary = (
                f"Chief Complaint: {chief_complaint}\n"
                f"Duration: Not reported\n"
                f"Severity (1-10): Not reported\n"
                f"Progression: Not reported\n"
                f"Affected Body Part: Not reported\n"
                f"Onset Type: Not reported\n"
                f"Associated Symptoms: Not reported\n"
                f"Clinical Note: Urgent keyword trigger ('{urgent_detected['keyword']}'). Intake stopped for immediate medical attention."
            )

            update_symptom_record(session_id, {
                "chief_complaint": chief_complaint,
                "risk_level": risk_result["risk_level"],
                "risk_reason": risk_result["reason"],
                "recommended_action": risk_result["recommended_action"],
                "summary": urgent_summary,
            })

            response_text = (
                "Important: your symptoms need urgent medical attention. "
                f"{risk_result['recommended_action']}"
            )
            update_session_state(session_id, STATES["COMPLETE"])

        elif not response_text:
            # Extract symptoms from user input
            extracted = llm.extract_symptoms(
                memory.conversation_history,
                user_input,
                session_id
            )

            # Update memory with extracted data
            if extracted:
                memory.update_fields(extracted)

            # Deterministic fallback extraction for short/natural replies that LLM may miss
            fallback_updates: Dict[str, Any] = {}
            currently_missing = memory.get_missing_fields()

            if "severity" in currently_missing:
                severity_value = _extract_severity_value(user_input or "")
                if severity_value is not None:
                    fallback_updates["severity"] = severity_value

            if "associated_symptoms" in currently_missing:
                associated = _extract_associated_symptoms(user_input or "")
                if associated is not None:
                    fallback_updates["associated_symptoms"] = associated

            if fallback_updates:
                memory.update_fields(fallback_updates)

            from config import EMERGENCY_CONTEXTS, EMERGENCY_FIELDS
            context_name = llm._detect_symptom_context(memory.conversation_history)
            is_emergency = context_name in EMERGENCY_CONTEXTS

            if is_emergency:
                missing_fields = [f for f in EMERGENCY_FIELDS if f in memory.get_missing_fields()]
            else:
                missing_fields = memory.get_missing_fields()

            # Check if intake is complete for the current context
            if not missing_fields:
                symptom_data = memory.get_symptom_data()
                # If it's an emergency, it's considered a partial record compared to the 7 generic fields
                _finalize_intake(symptom_data, partial=(is_emergency or not memory.is_intake_complete()))

            else:
                # Ask clarification questions for the remaining fields
                # CRITICAL: If chief_complaint is missing, STAY on it.
                if "chief_complaint" in missing_fields:
                    # Only mark chief_complaint as asked if it wasn't already.
                    # But we'll keep asking it until we get it.
                    if "chief_complaint" not in memory.asked_fields:
                        memory.mark_field_asked("chief_complaint")
                    
                    response_text = llm.generate_clarification_question(
                        ["chief_complaint"],
                        memory.conversation_history,
                        session_id
                    )
                    update_session_state(session_id, STATES["CLARIFYING"])
                
                else:
                    # Chief complaint is present, look for other UNASKED fields
                    unasked_missing = [f for f in missing_fields if f not in memory.asked_fields]

                    if unasked_missing:
                        # Pick ONLY the highest priority unasked field to mark as asked
                        # Sort by priority and pick the first
                        next_field = sorted(unasked_missing, key=lambda x: FIELD_PRIORITY.get(x, 99))[0]
                        memory.mark_field_asked(next_field)
                        
                        # Generate clarification question for only the next targeted field
                        response_text = llm.generate_clarification_question(
                            [next_field],
                            memory.conversation_history,
                            session_id
                        )
                        update_session_state(session_id, STATES["CLARIFYING"])
                    else:
                        # All missing fields were asked before, but still not filled.
                        # Re-ask the highest-priority missing field instead of finalizing.
                        next_missing = sorted(missing_fields, key=lambda x: FIELD_PRIORITY.get(x, 99))[0]
                        response_text = llm.generate_clarification_question(
                            [next_missing],
                            memory.conversation_history,
                            session_id
                        )
                        update_session_state(session_id, STATES["CLARIFYING"])
    
    elif current_state == STATES["COMPLETE"]:
        # Session already complete
        user_lower = (user_input or "").lower().strip().strip('.,!?')
        affirmatives = ["yes", "yep", "y", "ok", "okay", "sure", "show", "report", "please"]
        if any(word in user_lower for word in affirmatives):
            symptom_data = memory.get_symptom_data()
            summary = symptom_data.get("summary", "Summary not available.")
            response_text = f"Here is your summary report:\n\n{summary}\n\nYou can view the full report using the 'Clinical Report' button."
        else:
            response_text = "Your symptom check is complete. You can view your report or switch to the Health Consult tab."
    
    else:
        # Unknown state, reset to greeting
        response_text = "Sorry, something went wrong. Let's start again. What problem are you having today?"
        update_session_state(session_id, STATES["COLLECTING"])
    
    # Save assistant response
    if response_text:
        save_turn(session_id, "assistant", response_text)
    
    # Get updated state
    final_state = get_session_state(session_id)
    is_complete = (final_state == STATES["COMPLETE"])

    # If in COMPLETE but we don't have risk/wellness in memory (subsequent turn), load them
    if (is_complete) and risk_assessment is None:
        symptom_data = memory.get_symptom_data()
        risk_assessment = risk.categorize_risk(symptom_data)
        # For wellness tips, we can re-generate if LOW/MODERATE
        if risk_assessment['risk_level'] in ["LOW", "MODERATE"]:
             wellness_tip = llm.generate_health_advice(symptom_data, session_id)
        else:
             wellness_tip = f"Please prioritize seeking medical evaluation as advised. {risk_assessment['recommended_action']}"
    
    return {
        "response_text": response_text,
        "state": final_state,
        "is_complete": is_complete,
        "risk_assessment": risk_assessment,
        "wellness_tip": wellness_tip
    }
