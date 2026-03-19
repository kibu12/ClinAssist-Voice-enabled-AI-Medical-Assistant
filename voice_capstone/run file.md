# ClinAssist Project Handoff Plan

## Objective
Prepare the ClinAssist project for smooth teammate onboarding, setup, and validation with minimal friction.

## Plan
1. Confirm repository handoff contents
   - Include backend, frontend, config files, and sample evaluation assets.
   - Ensure `.env` is excluded from sharing and `.env.example` is present if needed.

2. Dependency and runtime setup
   - Install dependencies using `requirements.txt`.
   - Verify Python version compatibility (3.11+).
   - Start server with `uvicorn main:app --reload`.

3. Environment configuration
   - Add valid `NEXUS_API_KEY` and `NEXUS_BASE_URL` in local `.env`.
   - Keep optional endpoint overrides ready for custom gateways.
   - Set STT mode/timeouts for expected performance.

4. Functional smoke test
   - Create a new session from UI.
   - Test text flow end-to-end.
   - Test voice recording and STT path.
   - Validate TTS playback and fallback speech.
   - Validate risk badge and export summary.

5. Safety and scope validation
   - Confirm disclaimer remains visible and non-diagnostic messaging is preserved.
   - Confirm urgent-keyword early-stop flow is active.
   - Confirm deterministic risk logic remains unchanged.

6. Performance sanity checks
   - Verify latency logs are being written.
   - Check STT/LLM/TTS timeout behavior under normal conditions.

7. Team handoff notes
   - Share startup commands and known troubleshooting steps.
   - Document expected API routes and model names.
   - Call out any open TODOs for UI polish or summary wording.

## Definition of Done
- Teammate can clone, configure env vars, install deps, run locally, and complete one full intake flow (text and voice) without code changes.
- Exported summary is generated and risk categorization appears correctly.
- No blocking runtime errors during baseline usage.
