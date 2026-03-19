"""
Text-to-Speech module for ClinAssist
Uses gpt-4o-mini-tts model via Nexus API for speech synthesis
"""
import time
import requests
import base64
from requests.adapters import HTTPAdapter
from datetime import datetime
from typing import Optional
from config import NEXUS_BASE_URL, NEXUS_API_KEY, NEXUS_TTS_PATH, TTS_MODEL, TTS_VOICE, AUDIO_OUTPUT_DIR, TTS_TIMEOUT_SECONDS
from database import log_latency


HTTP_SESSION = requests.Session()
HTTP_ADAPTER = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=0)
HTTP_SESSION.mount("http://", HTTP_ADAPTER)
HTTP_SESSION.mount("https://", HTTP_ADAPTER)


def generate_speech(text: str, session_id: str) -> Optional[bytes]:
    """
    Generate speech audio from text using gpt-4o-mini-tts via Nexus API
    
    Args:
        text: Text to convert to speech
        session_id: Session ID for latency logging and file naming
    
    Returns:
        Raw audio bytes (MP3 format) or None on error
    """
    start_time = time.time()
    
    try:
        # Prepare request payload for Nexus API
        payload = {
            "model": TTS_MODEL,
            "input": text,
            "voice": TTS_VOICE,
            "response_format": "mp3"
        }
        
        headers = {
            "Authorization": f"Bearer {NEXUS_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Call Nexus API endpoint for TTS
        response = HTTP_SESSION.post(
            f"{NEXUS_BASE_URL}{NEXUS_TTS_PATH}",
            json=payload,
            headers=headers,
            timeout=TTS_TIMEOUT_SECONDS
        )
        
        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000
        log_latency(session_id, "tts", latency_ms)
        
        response.raise_for_status()
        
        # Get audio bytes
        audio_bytes = response.content
        
        # Save to file
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_path = AUDIO_OUTPUT_DIR / f"{session_id}_{timestamp}.mp3"
        
        with open(output_path, "wb") as f:
            f.write(audio_bytes)
        
        return audio_bytes
    
    except requests.exceptions.RequestException as e:
        error_body = ""
        resp = getattr(e, "response", None)
        if resp is not None:
            try:
                error_body = resp.text
            except Exception:
                error_body = ""
        print(f"TTS API Error: {e} | Response: {error_body}")
        latency_ms = (time.time() - start_time) * 1000
        log_latency(session_id, "tts_error", latency_ms)
        return None
    
    except Exception as e:
        print(f"TTS Error: {e}")
        latency_ms = (time.time() - start_time) * 1000
        log_latency(session_id, "tts_error", latency_ms)
        return None
