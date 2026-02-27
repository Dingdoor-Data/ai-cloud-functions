import time
import requests
from firebase_functions import https_fn
import uuid
from firebase_admin import initialize_app, firestore
from utils.agents_name import agents_name
from services.agents_services import _build_tools_summary
from config.config import (
    ai_post_call_collection,
    ELEVENLABS_API_KEY,
    BACKFILL_SECRET,
    DEFAULT_AGENT_IDS,
)


initialize_app()
db = firestore.client()

BASE = "https://api.elevenlabs.io"
HEADERS = {"xi-api-key": ELEVENLABS_API_KEY}

def _list_conversations(agent_id: str, cursor: str | None = None, page_size: int = 100) -> dict:
    params = {"page_size": page_size}
    if agent_id:
        params["agent_id"] = agent_id
    if cursor:
        params["cursor"] = cursor

    # GET /v1/convai/conversations
    r = requests.get(
        f"{BASE}/v1/convai/conversations",
        headers=HEADERS,
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _get_conversation(conversation_id: str) -> dict:
    # GET /v1/convai/conversations/{conversation_id}
    r = requests.get(
        f"{BASE}/v1/convai/conversations/{conversation_id}",
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _conversation_exists(conversation_id: str) -> bool:
    """
    Since we store docs with UUID ids, we dedupe by querying for an existing doc
    with conversationId == conversation_id.
    """
    q = (
        db.collection(ai_post_call_collection)
        .where("conversationId", "==", conversation_id)
        .limit(1)
    )
    # stream() yields docs; if any exists => already inserted
    return any(True for _ in q.stream())


@https_fn.on_request()
def elevenlabs_backfill_conversations(req: https_fn.Request) -> https_fn.Response:
    if req.method != "POST":
        return https_fn.Response("Method Not Allowed", status=405)

    # Manual trigger protection
    if BACKFILL_SECRET:
        provided = req.headers.get("x-backfill-secret") or ""
        if provided != BACKFILL_SECRET:
            return https_fn.Response("Unauthorized", status=401)

    body = req.get_json(silent=True) or {}

    agent_ids = body.get("agentIds") or DEFAULT_AGENT_IDS
    if not agent_ids:
        return https_fn.Response("No agent IDs provided", status=400)

    max_pages = int(body.get("maxPagesPerAgent") or 10)
    page_size = int(body.get("pageSize") or 100)

    inserted = 0
    skipped_existing = 0
    scanned = 0
    errors = 0

    for agent_id in agent_ids:
        cursor = None
        pages = 0

        while pages < max_pages:
            payload = _list_conversations(agent_id=agent_id, cursor=cursor, page_size=page_size)

            conversations = payload.get("conversations") or payload.get("results") or []
            scanned += len(conversations)

            for item in conversations:
                conversation_id = item.get("conversation_id") or item.get("conversationId")
                if not conversation_id:
                    continue

                # Dedupe by conversationId field
                if _conversation_exists(conversation_id):
                    skipped_existing += 1
                    continue

                try:
                    full = _get_conversation(conversation_id)

                    transcript_turns = full.get("transcript") or []
                    tools = _build_tools_summary(transcript_turns)
                    transcript_summary = ((full.get("analysis") or {}).get("transcript_summary"))

                    phone_call = (full.get("metadata", {}) or {}).get("phone_call") or {}

                    # store unix seconds like 1769617330
                    created_at = (
                        full.get("start_time_unix_secs")
                        or (full.get("metadata") or {}).get("start_time_unix_secs")
                    )
                    created_at = int(created_at) if created_at is not None else None

                    call_doc = {
                        "type": "backfill",
                        "createdAt": created_at,
                        "agentId": full.get("agent_id"),
                        "agentName": agents_name.get(full.get("agent_id"), ""),
                        "conversationId": conversation_id,
                        "status": full.get("status"),
                        "userNumber": phone_call.get("external_number"),
                        "callDurationSecs": (full.get("metadata", {}) or {}).get("call_duration_secs"),
                        "cost": (full.get("metadata", {}) or {}).get("cost"),
                        "transcript": transcript_summary,
                        "tools": tools,
                    }

                    doc_id = str(uuid.uuid4())
                    db.collection(ai_post_call_collection).document(doc_id).set(call_doc, merge=True)
                    inserted += 1

                except Exception:
                    errors += 1
                    # keep going (manual backfill shouldn’t fail the whole run)

            cursor = payload.get("next_cursor") or payload.get("cursor")
            has_more = payload.get("has_more")

            pages += 1
            if not has_more or not cursor:
                break

            time.sleep(0.2)

    return https_fn.Response(
        f"ok | agents={len(agent_ids)} scanned={scanned} inserted={inserted} "
        f"skipped_existing={skipped_existing} errors={errors}",
        status=200,
    )
