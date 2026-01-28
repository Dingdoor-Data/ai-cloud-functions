from dotenv import load_dotenv
load_dotenv()
import os

ai_post_call_collection = os.environ.get("AI_ASSISTANT_CALLS_COLLECTION", "aiAgentCalls")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
SIGNATURE_TOLERANCE_SECS = 30 * 60
BACKFILL_SECRET = os.environ.get("BACKFILL_SECRET", "")
DEFAULT_AGENT_IDS = [
    s.strip() for s in os.environ.get("ELEVENLABS_AGENT_IDS", "").split(",") if s.strip()
]