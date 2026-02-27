# ai_chat_service.py
import logging
import os
import requests
from firebase_admin import firestore
import uuid
from typing import List, Dict, Optional, Tuple, Any
import json

FileTuple = Tuple[str, bytes, str]  # (filename, data, content_type)


def _required_env(var_name: str) -> str:
    value = os.getenv(var_name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {var_name}")
    return value


AI_ASSISTANT_MESSAGES_COLLECTION = os.getenv("AI_ASSISTANT_MESSAGES_COLLECTION", "aiAssistantMessages")
AI_TEXT_ASSISTANT_URL = _required_env("AI_TEXT_ASSISTANT_URL")
AI_REQUEST_ENHANCED_URL = _required_env("AI_REQUEST_ENHANCED_URL")
AI_HUMAN_HANDOFF_URL = _required_env("AI_HUMAN_HANDOFF_URL")

class AiChatService:
    def __init__(self):
        self.db = firestore.client()

    def get_conversation_history(self, chat_id: str, limit: int = 20) -> List[Dict]:
        if not chat_id:
            return []
        try:
            messages_ref = self.db.collection(AI_ASSISTANT_MESSAGES_COLLECTION).document(chat_id).collection("messages")
            docs = messages_ref.order_by("timestamp", direction=firestore.Query.ASCENDING).limit(limit).get()
            formatted = []
            for doc in docs:
                d = doc.to_dict()
                if d.get("isCxInteraction") is True:
                    continue
                
                if d.get("event") == "humanAgentJoined":
                   continue

                formatted.append({
                    "role": d.get("role"),
                    "output": d.get("content"),
                    "attachments": d.get("attachments") or [],   
                })
            logging.info(f"Retrieved {len(formatted)} messages for chat_id {chat_id}")
            return formatted
        except Exception as e:
            logging.error(f"Error retrieving conversation history: {e}")
            return []

    def _post_json(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        headers = {'Content-Type': 'application/json'}
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def _post_multipart(
        self,
        url: str,
        user_id: str,
        message: str,
        previous_messages: Optional[List[Dict]] = None,
        files: Optional[List[FileTuple]] = None,
        chat_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Sends a multipart request to /chat with both text fields and files.
        - 'files' should be a list of (filename, bytes, content_type)
        """
        data = {
            "userId": user_id,
            "message": message,
        }
        if chat_id:
            data["id"] = chat_id
        if previous_messages:
            # backend expects previousMessages as a JSON string form field
            data["previousMessages"] = json.dumps(previous_messages)

        multipart_files = []
        for (fname, blob, ctype) in (files or []):
            multipart_files.append(("files", (fname, blob, ctype)))

        resp = requests.post(url, data=data, files=multipart_files, timeout=120)
        resp.raise_for_status()
        return resp.json()

    def send_message_to_assistant(
        self,
        chat_id: Optional[str],
        user_id: str,
        message: str,
        previous_messages: Optional[List[Dict]] = None,
        files: Optional[List[Tuple[str, bytes, str]]] = None,  # (filename, bytes, content_type)
        timeout_seconds: int = 60,
    ) -> Dict:
        """
        Sends a message (and optional files) to the agent service.

        If `previous_messages` is empty and `chat_id` exists, it backfills history
        from Firestore so the model keeps context.

        Payloads:
        - JSON (no files):
          {
            "id": chat_id?,
            "userId": user_id,
            "message": "...",
            "previousMessages": [{"role":"user|assistant","output":"..."}]?
          }

        - multipart/form-data (with files):
          fields:
            userId, message, id?, previousMessages(JSON string)?
          files:
            repeated field name "files" for each upload
        """
        if not user_id:
            raise ValueError("Missing required field: 'userId'")
        if not message or not isinstance(message, str):
            raise ValueError("Missing or invalid field: 'message'")

        # Backfill history if the client did not send it
        if (not previous_messages) and chat_id:
            previous_messages = self.get_conversation_history(chat_id)

        url = AI_TEXT_ASSISTANT_URL

        try:
            if files and len(files) > 0:
                # ---- multipart form (text + files) ----
                form: Dict[str, str] = {
                    "userId": user_id,
                    "message": message,
                }
                if chat_id:
                    form["id"] = chat_id
                if previous_messages:
                    form["previousMessages"] = json.dumps(previous_messages)

                # requests expects a list of ("files", (filename, bytes, content_type)) tuples
                multipart_files = [
                    ("files", (fname, blob_bytes, content_type or "application/octet-stream"))
                    for (fname, blob_bytes, content_type) in files
                ]

                resp = requests.post(
                    url,
                    data=form,
                    files=multipart_files,
                    timeout=timeout_seconds,
                )
            else:
                # ---- pure JSON (no files) ----
                payload: Dict = {
                    "userId": user_id,
                    "message": message,
                }
                if chat_id:
                    payload["id"] = chat_id
                if previous_messages:
                    payload["previousMessages"] = previous_messages

                resp = requests.post(
                    url,
                    json=payload,
                    timeout=timeout_seconds,
                )

            resp.raise_for_status()
            return resp.json()

        except requests.RequestException as e:
            logging.error(f"Assistant API request failed: {e}")
            raise RuntimeError(f"Assistant service error: {str(e)}")

    def get_summary_for_cta(self, message: str,locale: str = "en"):
        if not message:
            logging.warning("Empty message provided for CTA summary")
            return {"data": {"summary": "", "inferredCategory": {}}}
        interaction_id = f'text_assistant_{str(uuid.uuid4())}'
        data = {
            "initialRequest": message,
            "locale": locale,
            "responseDetails": [],
            "interactionId": interaction_id,
        }
        try:
            url = AI_REQUEST_ENHANCED_URL
            headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer 123'}
            resp = requests.post(url, json=data, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            logging.error("Enhanced API request timed out after 30s")
            return {"data": {"summary": "", "inferredCategory": {}}}
        except requests.RequestException as e:
            logging.error(f"Enhanced request failed: {e}")
            return {"data": {"summary": "", "inferredCategory": {}}}

    def handoff_human(self, chatId: str, reason: str):
        if not chatId:
            raise ValueError("Missing required field: 'chatId'")
        if not reason:
            raise ValueError("Missing required field: 'reason'")
        try:   
            url = AI_HUMAN_HANDOFF_URL
            data = {
                "chatId": chatId,
                "reason": reason,
            }
            headers = {'Content-Type': 'application/json'}
            resp = requests.post(url, json=data, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logging.error(f"Handoff human request failed: {e}")
            raise RuntimeError(f"Handoff service error: {str(e)}")
