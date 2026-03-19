"""
ClinAssist - Speech-Driven Structured Clinical Intake System
Main FastAPI application with all endpoints
"""
from fastapi import FastAPI, UploadFile, File, HTTPException, Path as FastAPIPath, status, File as FastAPIFile, Form, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from datetime import datetime
from pathlib import Path
import base64
import time
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Import models and modules
from models import (
    SessionCreate, TextInput, SessionResponse, SummaryResponse, ConsultRequest, ConsultResponse,
    ConsultVoiceResponse, HealthResponse, ErrorResponse, LatencyBreakdown, RiskAssessment,
    SymptomRecord, SessionHistoryResponse, FullSessionResponse
)
import database
import stt
import tts
import intake
from memory import SessionMemory
from config import SAFETY_DISCLAIMER, ENABLE_TTS_FOR_TEXT


# Initialize FastAPI app
app = FastAPI(
    title="ClinAssist API",
    description="Speech-Driven Structured Clinical Intake System",
    version="1.0.0"
)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize database and directories on startup"""
    database.init_database()
    print("Database initialized successfully")
    print(f"Safety Disclaimer: {SAFETY_DISCLAIMER}")


@app.get("/")
async def root():
    """Root endpoint - redirect to static frontend"""
    return RedirectResponse(url="/static/index.html", status_code=307)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/session/new", response_model=SessionCreate)
async def create_new_session():
    """Create a new intake session"""
    try:
        session_id = database.create_session(session_type="intake")
        return {
            "session_id": session_id,
            "message": "Session created successfully"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Session creation failed", "detail": str(e)}
        )


@app.post("/session/{session_id}/voice", response_model=SessionResponse)
async def process_voice_input(
    session_id: str = FastAPIPath(..., description="Session ID"),
    audio: UploadFile = File(..., description="Audio file (WAV format)")
):
    """
    Process voice input through complete pipeline: STT → Intake → TTS
    """
    total_start = time.time()
    latency = {"stt_ms": None, "llm_ms": None, "tts_ms": None, "total_ms": 0}
    
    try:
        # Validate session exists
        if not database.session_exists(session_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Session not found", "detail": f"Session {session_id} does not exist"}
            )
        
        # Read audio bytes
        audio_bytes = await audio.read()
        
        # Validate audio format
        if not stt.validate_audio_format(audio_bytes):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "Invalid audio format", "detail": "Audio must be WAV format (16-bit PCM, 16kHz, mono)"}
            )
        
        # STT: Transcribe audio
        stt_start = time.time()
        transcript = stt.transcribe_audio(audio_bytes, session_id)
        latency["stt_ms"] = (time.time() - stt_start) * 1000
        
        if not transcript:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "Transcription failed", "detail": "Could not transcribe audio"}
            )
        
        # Process through intake state machine
        llm_start = time.time()
        result = intake.process_interaction(session_id, transcript)
        latency["llm_ms"] = (time.time() - llm_start) * 1000
        
        # TTS: Generate speech response (optional for text mode to reduce latency)
        audio_base64 = None
        if ENABLE_TTS_FOR_TEXT:
            tts_start = time.time()
            audio_bytes = tts.generate_speech(result["response_text"], session_id)
            latency["tts_ms"] = (time.time() - tts_start) * 1000
            if audio_bytes:
                audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        else:
            latency["tts_ms"] = 0.0
        
        # Calculate total latency
        latency["total_ms"] = (time.time() - total_start) * 1000
        
        # Get symptom progress
        memory = SessionMemory(session_id)
        symptom_progress = memory.get_progress()
        
        # Build response
        response_data = {
            "transcript": transcript,
            "response_text": result["response_text"],
            "audio_base64": audio_base64,
            "state": result["state"],
            "is_complete": result["is_complete"],
            "risk_assessment": result.get("risk_assessment"),
            "latency_breakdown": latency,
            "symptom_progress": symptom_progress,
            "wellness_tip": result.get("wellness_tip")
        }
        
        return response_data
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Voice processing failed", "detail": str(e)}
        )


@app.post("/session/{session_id}/text", response_model=SessionResponse)
async def process_text_input(
    input_data: TextInput,
    session_id: str = FastAPIPath(..., description="Session ID")
):
    """
    Process text input (skip STT, use Intake → TTS)
    """
    total_start = time.time()
    latency = {"stt_ms": None, "llm_ms": None, "tts_ms": None, "total_ms": 0}
    
    try:
        # Validate session exists
        if not database.session_exists(session_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Session not found", "detail": f"Session {session_id} does not exist"}
            )
        
        text = input_data.text if input_data else ""
        current_state = database.get_session_state(session_id)

        if not text.strip() and current_state != "greeting":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": "Empty input", "detail": "Text input cannot be empty"}
            )
        
        # Process through intake state machine
        llm_start = time.time()
        result = intake.process_interaction(session_id, text)
        latency["llm_ms"] = (time.time() - llm_start) * 1000
        
        # TTS: Generate speech response
        tts_start = time.time()
        audio_bytes = tts.generate_speech(result["response_text"], session_id)
        latency["tts_ms"] = (time.time() - tts_start) * 1000
        
        audio_base64 = None
        if audio_bytes:
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        
        # Calculate total latency
        latency["total_ms"] = (time.time() - total_start) * 1000
        
        # Get symptom progress
        memory = SessionMemory(session_id)
        symptom_progress = memory.get_progress()
        
        # Build response
        response_data = {
            "transcript": text,
            "response_text": result["response_text"],
            "audio_base64": audio_base64,
            "state": result["state"],
            "is_complete": result["is_complete"],
            "risk_assessment": result.get("risk_assessment"),
            "latency_breakdown": latency,
            "symptom_progress": symptom_progress,
            "wellness_tip": result.get("wellness_tip")
        }
        
        return response_data
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Text processing failed", "detail": str(e)}
        )


@app.get("/session/{session_id}/summary", response_model=SummaryResponse)
async def get_session_summary(
    session_id: str = FastAPIPath(..., description="Session ID")
):
    """Get session summary with symptom record and risk assessment"""
    try:
        if not database.session_exists(session_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Session not found", "detail": f"Session {session_id} does not exist"}
            )
        
        symptom_record = database.get_symptom_record(session_id)
        session_state = database.get_session_state(session_id)
        
        if not symptom_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Symptom record not found", "detail": f"No symptom data for session {session_id}"}
            )
        
        # Extract risk assessment if available
        risk_assessment = None
        if symptom_record.get("risk_level"):
            risk_assessment = {
                "risk_level": symptom_record["risk_level"],
                "reason": symptom_record.get("risk_reason", ""),
                "recommended_action": symptom_record.get("recommended_action", "")
            }
        
        # Normalize potentially legacy values to keep summary endpoint robust
        progression_value = symptom_record.get("progression")
        if progression_value not in {"improving", "worsening", "stable"}:
            progression_value = None

        onset_value = symptom_record.get("onset_type")
        if onset_value not in {"sudden", "gradual"}:
            onset_value = None

        associated_value = symptom_record.get("associated_symptoms")
        if isinstance(associated_value, str):
            associated_value = [associated_value]
        if associated_value is not None and not isinstance(associated_value, list):
            associated_value = None

        # Build symptom record response
        symptom_data = SymptomRecord(
            chief_complaint=symptom_record.get("chief_complaint"),
            duration=symptom_record.get("duration"),
            severity=symptom_record.get("severity"),
            progression=progression_value,
            associated_symptoms=associated_value,
            affected_body_part=symptom_record.get("affected_body_part"),
            onset_type=onset_value
        )
        
        return {
            "session_id": session_id,
            "symptom_record": symptom_data,
            "risk_assessment": risk_assessment,
            "summary": symptom_record.get("summary") if symptom_record else None,
            "state": session_state
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Summary retrieval failed", "detail": str(e)}
        )


@app.post("/consult", response_model=ConsultResponse)
async def process_standalone_consult(
    request: ConsultRequest
):
    """
    Process standalone Health Consult (general health/fitness Q&A)
    """
    try:
        import llm
        import database
        
        # Optional context from intake session
        symptom_data = None
        history = []
        context_session_id = request.context_session_id
        if not context_session_id and request.session_id and database.session_exists(request.session_id):
            if database.get_session_type(request.session_id) == "intake":
                context_session_id = request.session_id

        if context_session_id and database.session_exists(context_session_id):
            memory = SessionMemory(context_session_id)
            symptom_data = memory.get_symptom_data()
            history = memory.conversation_history

        # Use only consult session ids for consult conversation history
        if (
            request.session_id
            and database.session_exists(request.session_id)
            and database.get_session_type(request.session_id) == "consult"
        ):
            session_id = request.session_id
        else:
            session_id = f"consult_{int(time.time())}"
            database.create_session(session_id, session_type="consult")
            
        # Log the user's question
        database.save_turn(session_id, "user", request.question)
        
        answer = llm.respond_to_consult(
            request.question,
            symptom_data,
            history
        )
        
        # Log the bot's response
        database.save_turn(session_id, "assistant", answer)
        
        # TTS: Generate speech response (optional for text mode)
        audio_base64 = None
        if ENABLE_TTS_FOR_TEXT:
            try:
                import tts
                audio_bytes = tts.generate_speech(answer, session_id)
                if audio_bytes:
                    audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
            except Exception as e:
                logger.error(f"Failed to generate TTS for consult: {e}")
        
        return {
            "answer": answer,
            "audio_base64": audio_base64,
            "session_id": session_id
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "Consult processing failed", "detail": str(e)}
        )


@app.post("/consult/voice", response_model=ConsultVoiceResponse)
async def process_standalone_voice_consult(
    audio: UploadFile = FastAPIFile(...),
    session_id: Optional[str] = Form(None),
    context_session_id: Optional[str] = Form(None)
):
    """
    Process standalone Health Consult using voice input
    """
    try:
        import stt
        import llm
        import tts
        import database
        
        # 1. Read Audio
        audio_content = await audio.read()
        if not audio_content:
            raise HTTPException(status_code=400, detail="Empty audio file")
            
        temp_session = f"consult_{int(time.time())}"
        
        # 2. STT
        transcript = stt.transcribe_audio(audio_content, temp_session)
        if not transcript or not transcript.strip():
            return {
                "answer": "I couldn't hear you clearly. Could you please repeat that?",
                "transcript": "",
                "audio_base64": None
            }
            
        # 3. Context gathering
        symptom_data = None
        history = []
        actual_context_session_id = context_session_id
        if not actual_context_session_id and session_id and database.session_exists(session_id):
            if database.get_session_type(session_id) == "intake":
                actual_context_session_id = session_id

        if actual_context_session_id and database.session_exists(actual_context_session_id):
            memory = SessionMemory(actual_context_session_id)
            symptom_data = memory.get_symptom_data()
            history = memory.conversation_history

        if session_id and database.session_exists(session_id) and database.get_session_type(session_id) == "consult":
            actual_session_id = session_id
        else:
            actual_session_id = temp_session
            database.create_session(actual_session_id, session_type="consult")
            
        # Log user question
        database.save_turn(actual_session_id, "user", transcript)
            
        # 4. LLM
        answer = llm.respond_to_consult(
            transcript,
            symptom_data,
            history
        )
        
        # Log assistant response
        database.save_turn(actual_session_id, "assistant", answer)
        
        # 5. TTS
        audio_base64 = None
        audio_bytes = tts.generate_speech(answer, actual_session_id)
        if audio_bytes:
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
        
        return {
            "answer": answer,
            "transcript": transcript,
            "audio_base64": audio_base64,
            "session_id": actual_session_id
        }
        
    except Exception as e:
        logger.error(f"Consult voice error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Voice consult processing failed", "detail": str(e)}
        )


@app.get("/sessions", response_model=SessionHistoryResponse)
async def list_sessions(
    session_type: Optional[str] = Query(None, description="Filter by session type: intake or consult")
):
    """List recent sessions"""
    if session_type and session_type not in {"intake", "consult"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "Invalid session type", "detail": "session_type must be 'intake' or 'consult'"}
        )

    sessions = database.get_recent_sessions(limit=20, session_type=session_type)
    return {"sessions": sessions}


@app.get("/session/{session_id}", response_model=FullSessionResponse)
async def get_session(session_id: str = FastAPIPath(..., description="Session ID")):
    """Get full session data including history and state"""
    data = database.get_session_export_data(session_id)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "Session not found", "detail": f"No session found with ID {session_id}"}
        )
    
    # Load state from database directly as export_data might have raw state
    state = database.get_session_state(session_id)
    
    # Reconstruct risk assessment and wellness tip if complete
    risk_assessment = None
    wellness_tip = None
    if state == "complete":
        import risk
        import llm
        symptom_data = data["symptom_record"]
        # Use existing risk data if available in symptom_record
        if symptom_data.get("risk_level"):
            risk_assessment = {
                "risk_level": symptom_data["risk_level"],
                "reason": symptom_data.get("risk_reason", ""),
                "recommended_action": symptom_data.get("recommended_action", "")
            }
        else:
            risk_assessment = risk.categorize_risk(symptom_data)
            
        if risk_assessment['risk_level'] in ["LOW", "MODERATE"]:
            wellness_tip = llm.generate_health_advice(symptom_data, session_id)
        else:
            wellness_tip = f"Please prioritize seeking medical evaluation as advised. {risk_assessment['recommended_action']}"

    return {
        "session_id": data["session_id"],
        "created_at": data["created_at"],
        "state": state,
        "conversation_history": data["conversation_history"],
        "symptom_record": data["symptom_record"],
        "risk_assessment": risk_assessment,
        "wellness_tip": wellness_tip
    }


@app.get("/session/{session_id}/export", response_class=PlainTextResponse)
async def export_session(
    session_id: str = FastAPIPath(..., description="Session ID")
):
    """Export session data in doctor-ready text format"""
    try:
        if not database.session_exists(session_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Session not found", "detail": f"Session {session_id} does not exist"}
            )
        
        export_data = database.get_session_export_data(session_id)
        
        if not export_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "Export failed", "detail": "No data available for export"}
            )
        
        # Format as doctor-ready report
        report_lines = []
        report_lines.append("=" * 70)
        report_lines.append("CLINASSIST - PATIENT INTAKE SUMMARY")
        report_lines.append("=" * 70)
        report_lines.append(f"Session ID: {export_data['session_id']}")
        report_lines.append(f"Date: {export_data['created_at']}")
        report_lines.append(f"Status: {export_data['state'].upper()}")
        report_lines.append("")
        report_lines.append("IMPORTANT DISCLAIMER:")
        report_lines.append(SAFETY_DISCLAIMER)
        report_lines.append("")
        report_lines.append("-" * 70)
        report_lines.append("STRUCTURED SYMPTOM DATA")
        report_lines.append("-" * 70)
        
        symptom_record = export_data["symptom_record"]
        report_lines.append(f"Chief Complaint: {symptom_record.get('chief_complaint', 'Not provided')}")
        report_lines.append(f"Duration: {symptom_record.get('duration', 'Not provided')}")
        report_lines.append(f"Severity: {symptom_record.get('severity', 'Not provided')}/10")
        report_lines.append(f"Progression: {symptom_record.get('progression', 'Not provided')}")
        report_lines.append(f"Affected Body Part: {symptom_record.get('affected_body_part', 'Not provided')}")
        report_lines.append(f"Onset Type: {symptom_record.get('onset_type', 'Not provided')}")
        
        associated = symptom_record.get('associated_symptoms', [])
        if associated:
            report_lines.append(f"Associated Symptoms: {', '.join(associated)}")
        else:
            report_lines.append("Associated Symptoms: None reported")
        
        report_lines.append("")
        report_lines.append("-" * 70)
        report_lines.append("RISK ASSESSMENT")
        report_lines.append("-" * 70)
        
        if symptom_record.get('risk_level'):
            report_lines.append(f"Risk Level: {symptom_record['risk_level']}")
            report_lines.append(f"Reason: {symptom_record.get('risk_reason', 'Not provided')}")
            report_lines.append(f"Recommended Action: {symptom_record.get('recommended_action', 'Not provided')}")
        else:
            report_lines.append("Risk assessment not yet completed")
        
        report_lines.append("")
        report_lines.append("-" * 70)
        report_lines.append("CLINICAL SUMMARY")
        report_lines.append("-" * 70)
        
        if symptom_record.get('summary'):
            report_lines.append(symptom_record['summary'])
        else:
            report_lines.append("Summary not yet generated")
        
        report_lines.append("")
        report_lines.append("-" * 70)
        report_lines.append("CONVERSATION TRANSCRIPT")
        report_lines.append("-" * 70)
        
        for turn in export_data["conversation_history"]:
            role = turn["role"].upper()
            content = turn["content"]
            report_lines.append(f"{role}: {content}")
        
        report_lines.append("")
        report_lines.append("=" * 70)
        report_lines.append("END OF REPORT")
        report_lines.append("=" * 70)
        
        return "\n".join(report_lines)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "Export failed", "detail": str(e)}
        )


# Mount static files for frontend
static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_path), html=True), name="static")


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler for unhandled errors"""
    print(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal server error",
            "detail": str(exc)
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
