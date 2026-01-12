import os
from dotenv import load_dotenv
load_dotenv()
import json
import uuid
import time
import hmac
from hashlib import sha256
from firebase_functions import https_fn
from firebase_admin import initialize_app, firestore

initialize_app()
db = firestore.client()

ai_post_call_collection = os.environ.get("AI_ASSISTANT_CALLS_COLLECTION", "aiAgentCalls")
ELEVENLABS_WEBHOOK_SECRET = os.environ.get("ELEVENLABS_WEBHOOK_SECRET", "")
SIGNATURE_TOLERANCE_SECS = 30 * 60

def _safe_json_loads(value):
    if not value or not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None

def _build_tools_summary(transcript):
    tool_results = []
    for turn in transcript or []:
        tool_results.extend(turn.get("tool_results", []) or [])

    tools = []
    for idx, result in enumerate(tool_results):
        tool_name = result.get("tool_name")
        parsed_value = _safe_json_loads(result.get("result_value"))
        is_error = result.get("is_error") is True

        summary = None
        if idx == 0:
            summary = {
                "zipCode": None,
                "status": None,
            }
            if not is_error and isinstance(parsed_value, dict):
                summary["zipCode"] = parsed_value.get("zipCode")
                summary["status"] = parsed_value.get("status") or (
                    "success" if parsed_value.get("success") else None
                )
        elif idx == 1:
            summary = {
                "status": None,
                "data": {
                    "inferredCategory": None,
                    "summary": None,
                },
            }
            if not is_error and isinstance(parsed_value, dict):
                summary["status"] = parsed_value.get("status")
                data = parsed_value.get("data") or {}
                summary["data"]["inferredCategory"] = data.get("inferredCategory")
                summary["data"]["summary"] = data.get("summary")
        elif idx == 2:
            summary = {
                "status": None,
                "message": None,
                "data": {
                    "knockId": None,
                },
            }
            if not is_error and isinstance(parsed_value, dict):
                summary["status"] = parsed_value.get("status")
                summary["message"] = parsed_value.get("message")
                data = parsed_value.get("data") or {}
                summary["data"]["knockId"] = data.get("knockId")

        tools.append(
            {
                "toolName": tool_name,
                "result": summary,
                "isError": is_error,
            }
        )

    return tools

def _verify_elevenlabs_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    ElevenLabs-Signature format: t=timestamp,v0=hash
    where hash = hex(HMAC_SHA256(secret, f"{timestamp}.{request_body}"))
    """
    if not signature_header:
        return False

    parts = dict(p.split("=", 1) for p in signature_header.split(",") if "=" in p)
    timestamp = parts.get("t")
    provided_hash = parts.get("v0")
    if not timestamp or not provided_hash:
        return False

    # Timestamp check
    now = int(time.time())
    ts = int(timestamp)
    if ts < (now - SIGNATURE_TOLERANCE_SECS) or ts > (now + 60):
        return False

    signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}".encode("utf-8")
    mac = hmac.new(
        key=ELEVENLABS_WEBHOOK_SECRET.encode("utf-8"),
        msg=signed_payload,
        digestmod=sha256,
    ).hexdigest()

    return hmac.compare_digest(mac, provided_hash)

@https_fn.on_request()
def elevenlabs_post_call_webhook(req: https_fn.Request) -> https_fn.Response:
    if req.method != "POST":
        return https_fn.Response("Method Not Allowed", status=405)

    raw_body = req.get_data()  # bytes
    sig = req.headers.get("elevenlabs-signature") or req.headers.get("ElevenLabs-Signature")
    if not _verify_elevenlabs_signature(raw_body, sig):
        return https_fn.Response("Unauthorized", status=401)

    payload = req.get_json(silent=True)
    if payload is None:
        payload = json.loads(raw_body.decode("utf-8"))

    event_type = payload.get("type")
    event_ts = payload.get("event_timestamp")
    data = payload.get("data", {}) or {}
    transcript_turns = data.get("transcript") or []
    tools = _build_tools_summary(transcript_turns)
    transcript_summary = ((data.get("analysis") or {}).get("transcript_summary"))

    # Recommended: stable id for idempotency
    conversation_id = data.get("conversation_id") or data.get("conversationId")
    doc_id = str(uuid.uuid4())

    # Keep the stored document reasonably small (Firestore doc limit is 1MB).
    # Store full transcript only if you’re sure it won’t exceed limits.
    call_doc = {
        "type": event_type,
        "createdAt": event_ts,
        "agentId": data.get("agent_id"),
        "conversationId": conversation_id,
        "status": data.get("status"),
        "metadata": data.get("metadata", {}),
        "callDurationSecs": (data.get("metadata", {}) or {}).get("call_duration_secs"),
        "cost": (data.get("metadata", {}) or {}).get("cost"),
        "transcript": transcript_summary,
        "tools": tools
    }

    db.collection(ai_post_call_collection).document(doc_id).set(call_doc, merge=True)
    return https_fn.Response("ok", status=200)
