# send_text_assistant_message.py
from datetime import datetime, time as dtime, timezone
from zoneinfo import ZoneInfo
import functions_framework
from flask import make_response
from google.cloud import firestore
import logging
import time
import json
import markdown
import os
import uuid
import mimetypes
from services.ai_chat_service import AiChatService
from utils.ai_chat_utils import save_messages_to_firestore, update_chat_metadata
from google.cloud import storage 
from datetime import timedelta
from google.auth.transport.requests import Request
import google.auth

MIAMI_TZ = ZoneInfo("America/New_York")

OFFLINE_ES = """
Nuestro equipo no está disponible en este momento, pero te responderemos apenas volvamos. Nuestro tiempo de respuesta habitual es de menos de 2 horas entre las 9am y 5pm (Miami). Recibirás todas las actualizaciones por aquí.
"""

OFFLINE_EN = """
Our team's currently offline, but we'll hit you back first thing when we're back online. During business hours (9am-5pm Miami), we reply fast — usually under 2 hours. You'll get your updates right here.
"""

def _is_miami_business_hours(now_utc: datetime) -> bool:
    local = now_utc.astimezone(MIAMI_TZ)
    start = dtime(9, 0)
    end   = dtime(17, 0)
    return start <= local.time() < end


db = firestore.Client()
ai_chat_service = AiChatService()
FILES_BUCKET = os.getenv("FILES_BUCKET", "text-assistant-uploads")  # e.g. dingdoor-uploads
AI_ASSISTANT_MESSAGES_COLLECTION = os.getenv("AI_ASSISTANT_MESSAGES_COLLECTION", "aiAssistantMessages")

def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

# ---- helpers for GCS uploads ----
_storage_client = None
def _gcs():
    global _storage_client
    if _storage_client is None:
        _storage_client = storage.Client()
    return _storage_client

def _upload_to_bucket(bucket_name: str, blob_path: str, data: bytes, content_type: str) -> dict:
    bucket = _gcs().bucket(bucket_name)
    blob = bucket.blob(blob_path)
    blob.upload_from_string(data, content_type=content_type)
    blob.cache_control = "public, max-age=3600"
    blob.content_disposition = f'inline; filename="{os.path.basename(blob_path)}"'
    blob.patch()

    preview_url = None
    try:
        signer_email = os.getenv("SIGNED_URL_SA_EMAIL","bucket-manager-text-assistant@knock24-inc.iam.gserviceaccount.com")
        # IMPORTANT: request a token with the right scopes for IAMCredentials.signBlob
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]  # or "https://www.googleapis.com/auth/iam"
        creds, _ = google.auth.default(scopes=scopes)
        creds.refresh(Request())
        access_token = creds.token

        preview_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=int(os.getenv("SIGNED_URL_EXPIRES_HOURS", "72"))),
            method="GET",
            service_account_email=signer_email,
            access_token=access_token,  # forces IAM-backed signing (no local key)
        )
    except Exception as e:
        logging.warning(f"Could not generate signed URL for {blob_path}: {e}")

    return {
        "filename": os.path.basename(blob_path),
        "contentType": content_type,
        "bytes": len(data),
        "storagePath": blob_path,
        "gcsUri": f"gs://{bucket_name}/{blob_path}",
        "url": preview_url,
    }
    

@functions_framework.http
def ai_send_text_assistant_message(req):
    """
    Unified handler: accepts either JSON (text-only) or multipart/form-data (text + files).
    JSON payload (text-only):
      { "id": "chat_id"?, "userId": "...", "message": "...", "previousMessages": [...]? }

    Multipart form-data fields (for files):
      - userId: text
      - message: text
      - id: text (optional)
      - previousMessages: text JSON (optional)
      - files: file (repeatable) — images or PDFs
    """
    if req.method == 'OPTIONS':
        return add_cors_headers(make_response("", 204))

    try:
        content_type = (req.headers.get("Content-Type") or "").lower()
        attachments = []

        if "multipart/form-data" in content_type:
            form = req.form
            files = req.files
            user_id = form.get("userId")
            user_message = form.get("message")
            chat_id = form.get("id")
            
            if not user_id or not user_message:
                return add_cors_headers(make_response(json.dumps({"error": "userId and message are required"}), 400))

            prev_msgs = []
            prev_raw = form.get("previousMessages")
            if prev_raw:
                try:
                    prev_msgs = json.loads(prev_raw)
                except Exception:
                    return add_cors_headers(make_response(json.dumps({"error": "previousMessages must be JSON list"}), 400))

            file_list = []
            if files:
                for key in files:
                    incoming = files.getlist(key) if hasattr(files, "getlist") else [files[key]]
                    for f in incoming:
                        blob_bytes = f.read()
                        ctype = f.content_type or (mimetypes.guess_type(f.filename)[0] or "application/octet-stream")
                        fname = f.filename or f"upload-{uuid.uuid4().hex}"
                        file_list.append((fname, blob_bytes, ctype))

            called_at = int(time.time() * 1000)
            message_result = ai_chat_service.send_message_to_assistant(
                chat_id=chat_id,
                user_id=user_id,
                message=user_message,
                previous_messages=prev_msgs,
                files=file_list,
            )
            attachments_map = message_result.get("attachmentsMap") or []  # <- from chatbot
            
            assistant_message_timestamp = int(time.time() * 1000)

        else:
            if not req.is_json:
                return add_cors_headers(make_response(json.dumps({"error": "Missing JSON"}), 400))
            data = req.get_json()
            if not data:
                return add_cors_headers(make_response(json.dumps({"error": "Empty JSON body"}), 400))
            if 'userId' not in data or 'message' not in data:
                return add_cors_headers(make_response(json.dumps({"error": "userId and message are required"}), 400))

            chat_id = data.get("id")
            user_id = data.get("userId")
            user_message = data.get("message")
            prev_msgs = data.get("previousMessages") or []
            called_at = int(time.time() * 1000)
            message_result = ai_chat_service.send_message_to_assistant(
                chat_id=chat_id,
                user_id=user_id,
                message=user_message,
                previous_messages=prev_msgs,
                files=None,
            )
            
            assistant_message_timestamp = int(time.time() * 1000)

        token_usage = message_result.get("tokenUsage", "")
        result_id = message_result.get("id")
        result_reply = message_result.get("message", "")
        cta = message_result.get("cta", "")
        locale = message_result.get("locale", "en")

        conversation_id = result_id or chat_id or str(uuid.uuid4())
        chat_title = message_result.get("title", "New Chat")
        result_reply_html = markdown.markdown(result_reply)
        user_message_html = markdown.markdown(user_message)

        update_chat_metadata(
            db, conversation_id, user_id, result_reply_html or user_message_html,chat_title ,message_count=2
        )

        enhanced_request = {}
        #professional help CTA handling
        if cta == 'professional_help':
            summary = message_result.get("ctaData", "")
            if summary:
                enhanced_response = ai_chat_service.get_summary_for_cta(summary)
                if enhanced_response and isinstance(enhanced_response.get("data"), dict):
                    response_data = enhanced_response.get("data", {})
                    enhanced_request = {
                        "summary": response_data.get("summary", ""),
                        "inferredCategory": response_data.get("inferredCategory", {})
                    }
        # human_handoff processing
        offline_markdown = ""
        if cta == 'human_handoff':
            reason = message_result.get("ctaData", "User requested human handoff.")
            resp = ai_chat_service.handoff_human(conversation_id, reason=reason)
            logging.info(f"Human handoff requested for chat {conversation_id} with reason: {reason} at time {datetime.now(timezone.utc).isoformat()}")
            if not _is_miami_business_hours(datetime.now(timezone.utc)):
                logging.info(f"Outside Miami business hours, sending offline message for chat {conversation_id}")
                offline_msg = OFFLINE_ES if locale.startswith("es") else OFFLINE_EN
                offline_markdown = markdown.markdown(offline_msg)
                

        result_reply_clean = result_reply_html.replace("\n", "")

        messages_collection = db.collection(AI_ASSISTANT_MESSAGES_COLLECTION).document(conversation_id).collection('messages')
        user_message_ref = messages_collection.document()
        user_message_id = user_message_ref.id

        if FILES_BUCKET and 'file_list' in locals() and file_list:
            for (fname, blob_bytes, ctype) in file_list:
                storage_path = f"conversations/{user_id}/{conversation_id}/{user_message_id}/{fname}"
                meta = _upload_to_bucket(FILES_BUCKET, storage_path, blob_bytes, ctype)
                attachments.append(meta)
                
        if attachments and attachments_map:
            idx = {a.get("filename"): a for a in attachments_map if a.get("filename")}
            for a in attachments:
                match = idx.get(a.get("filename"))
                if match:
                    if match.get("fileId"):
                        a["fileId"] = match["fileId"]
                    if match.get("contentType") and not a.get("contentType"):
                        a["contentType"] = match["contentType"]       
                

        user_msg, assistant_msg = save_messages_to_firestore(
            db, messages_collection, user_message_ref, user_message_id, user_message_html, called_at, result_reply_clean,
            assistant_message_timestamp, 'requestService' if cta == "professional_help" else None,
            enhanced_request if cta == "professional_help" else {}, token_usage if token_usage else {},offline_markdown,
            attachments=attachments if attachments else None
        )

        return add_cors_headers(make_response(json.dumps({
            "success": True,
            "conversationId": conversation_id,
            "reply": result_reply_clean if not offline_markdown else offline_markdown,
            "replyId": assistant_msg["id"],
            "userMsgId": user_msg["id"],
            "event": "requestService" if cta == "professional_help" else "",
            "eventData": enhanced_request if cta == "professional_help" else {},
            "tokenUsage": token_usage
        }), 200))

    except Exception as e:
        logging.exception("Unexpected error in assistant message handler.")
        return add_cors_headers(make_response(json.dumps({"error": str(e)}), 500))
