import os
from dotenv import load_dotenv
load_dotenv()
import uuid
import time
import json
import hmac
from hashlib import sha256
from firebase_functions import https_fn
from firebase_admin import initialize_app, firestore
from utils.agents_name import agents_name
from services.agents_services import _build_tools_summary
from config.config import (
    ELEVENLABS_WEBHOOK_SECRET,
    SIGNATURE_TOLERANCE_SECS,
    ai_post_call_collection,
)

initialize_app()
db = firestore.client()

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

    raw_body = req.get_data()  
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

    conversation_id = data.get("conversation_id") or data.get("conversationId")
    doc_id = str(uuid.uuid4())

    phone_call = (data.get("metadata", {}) or {}).get("phone_call") or {}
    call_doc = {
        "type": event_type,
        "createdAt": event_ts,
        "agentId": data.get("agent_id"),
        "agentName": agents_name.get(data.get("agent_id"),""),
        "conversationId": conversation_id,
        "status": data.get("status"),
        "userNumber": phone_call.get("external_number"),
        "callDurationSecs": (data.get("metadata", {}) or {}).get("call_duration_secs"),
        "cost": (data.get("metadata", {}) or {}).get("cost"),
        "transcript": transcript_summary,
        "tools": tools
    }

    db.collection(ai_post_call_collection).document(doc_id).set(call_doc, merge=True)
    return https_fn.Response("ok", status=200)
