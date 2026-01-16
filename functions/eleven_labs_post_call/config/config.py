from dotenv import load_dotenv
load_dotenv()
import os

ai_post_call_collection = os.environ.get("AI_ASSISTANT_CALLS_COLLECTION", "aiAgentCalls")
ELEVENLABS_WEBHOOK_SECRET = os.environ.get("ELEVENLABS_WEBHOOK_SECRET", "")
SIGNATURE_TOLERANCE_SECS = 30 * 60