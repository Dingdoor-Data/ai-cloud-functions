import json
import os
import time
import uuid
import mimetypes
import logging
import markdown
import functions_framework
from flask import jsonify, make_response
from google.cloud import firestore
from google.cloud import storage
from datetime import timedelta
from google.auth.transport.requests import Request
import google.auth
from utils.ai_chat_utils import update_chat_metadata, save_messages_to_firestore


# ---- config ----
FILES_BUCKET = os.getenv("FILES_BUCKET","text_assistant_uploads")  # e.g. "text_assistant_uploads" (optional)
ROOT_COLLECTION = os.getenv("AI_ASSISTANT_MESSAGES_COLLECTION", "aiAssistantMessages")


def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "*"
    return resp

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
        signer_email = os.getenv("SIGNED_URL_SA_EMAIL","675741190048-compute@developer.gserviceaccount.com")
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
def ai_insert_text_assistant_message(request):
    # CORS preflight
    if request.method == "OPTIONS":
        return add_cors(make_response("", 204))

    try:
        db = firestore.Client()

        content_type = (request.headers.get("Content-Type") or "").lower()
        attachments = []

        # ---- parse input ----
        if "multipart/form-data" in content_type:
            form = request.form

            conversation_id = form.get("conversationId") or form.get("id") or str(uuid.uuid4())
            user_id = form.get("userId")
            role = (form.get("role") or "user").strip()
            message = form.get("message")
            event = form.get("event")
            event_data_raw = form.get("eventData")
            event_data = json.loads(event_data_raw) if event_data_raw else {}

            if not user_id or not message or not conversation_id:
                return add_cors(make_response(json.dumps({"error": "userId, message and id are required"}), 400))

            # Files: support either `files` repeated, or any file fields
            file_list = []
            if request.files:
                # If frontend uses name="files" multiple, this works:
                incoming = request.files.getlist("files") if hasattr(request.files, "getlist") else []
                # fallback: take all fields
                if not incoming:
                    incoming = list(request.files.values())

                for f in incoming:
                    blob_bytes = f.read()
                    ctype = f.content_type or (mimetypes.guess_type(f.filename)[0] or "application/octet-stream")
                    fname = f.filename or f"upload-{uuid.uuid4().hex}"
                    file_list.append((fname, blob_bytes, ctype))

        else:
            if not request.is_json:
                return add_cors(make_response(json.dumps({"error": "Missing JSON"}), 400))

            data = request.get_json(silent=True) or {}
            conversation_id = data.get("conversationId") or data.get("id") or str(uuid.uuid4())
            user_id = data.get("userId")
            role = (data.get("role") or "user").strip()
            message = data.get("message")
            event = data.get("event")
            event_data_raw = data.get("eventData")
            event_data = json.loads(event_data_raw) if event_data_raw else {}
            file_list = []  # JSON mode: no files

            if not user_id or not message or not conversation_id:
                return add_cors(make_response(json.dumps({"error": "userId and message are required"}), 400))

        if role not in ("user", "humanAgent", "system"):
            return add_cors(make_response(json.dumps({"error": "role must be 'user' or 'humanAgent'"}), 400))

        now_ms = int(time.time() * 1000)

        # ---- firestore paths ----
        chat_ref = db.collection(ROOT_COLLECTION).document(conversation_id)
        messages_col = chat_ref.collection("messages")
        msg_ref = messages_col.document()
        msg_id = msg_ref.id
        
        #update chat metadata
        update_chat_metadata(db, conversation_id, message)

        # ---- upload attachments (optional) ----
        if FILES_BUCKET and file_list:
            for (fname, blob_bytes, ctype) in file_list:
                storage_path = f"conversations/{user_id}/{conversation_id}/{msg_id}/{fname}"
                meta = _upload_to_bucket(FILES_BUCKET, storage_path, blob_bytes, ctype)
                attachments.append(meta)

        # save user message
        save_messages_to_firestore(
            db,
            messages_col,
            role,
            msg_ref,
            msg_id,
            message,
            now_ms,
            event=event,
            event_data=event_data,
            attachments=attachments,
        )

        return add_cors(jsonify({
            "success": True,
            "conversationId": conversation_id,
            "messageId": msg_id,
            "attachmentsCount": len(attachments),
        }))

    except Exception as e:
        logging.exception("ai_insert_text_assistant_message failed")
        return add_cors(make_response(json.dumps({"error": str(e)}), 500))
