import os
import datetime
import time
from google.cloud.firestore import Increment
from datetime import datetime
from models.ai_assistant_chat import AiAssistantMessage

AI_ASSISTANT_CHATS_COLLECTION = os.getenv("AI_ASSISTANT_CHATS_COLLECTION", "aiAssistantChats")

def save_messages_to_firestore(db,messages_collection, user_message_ref, user_message_id,user_message, user_timestamp, assistant_reply, assistant_timestamp, cta ,cta_data, token_usage,offline_msg="", attachments=None):
    """
    Save both user and assistant messages to Firestore
    in messages/{chatId}/messages/ collection
    """
    # Create message collection reference
    
    # Create user message
    user_message_data = AiAssistantMessage(
        role="user",
        content=user_message,
        timestamp=user_timestamp,
        tokenUsage=token_usage,
        id=user_message_id,  # Use the auto-generated ID
        attachments=attachments or [],
        isCxInteraction=False
    ).__dict__
    
    # Create assistant message
    assistant_message_ref = messages_collection.document()  # Auto-generate ID
    assistant_message_data = AiAssistantMessage(
        role="assistant", 
        content=assistant_reply if not offline_msg else offline_msg,
        event=cta,
        eventData=cta_data,
        tokenUsage=token_usage,
        timestamp=assistant_timestamp,
        id=assistant_message_ref.id,  # Use the auto-generated ID
        isCxInteraction=False
    ).__dict__
    
    # Use a batch write for efficiency
    batch = db.batch()
    batch.set(user_message_ref, user_message_data)
    batch.set(assistant_message_ref, assistant_message_data)
    batch.commit()

    return user_message_data, assistant_message_data


def update_chat_metadata(db, chat_id, user_id, last_message, title, message_count=2):
    """
    Updates or creates the chat document metadata in Firestore.
    
    Args:
        db: Firestore client instance
        chat_id: ID of the chat to update
        user_id: ID of the user who owns the chat
        message_count: Number of messages to add to the count (default=2 for user+assistant)
        
    Returns:
        The updated or created chat document data
    """
    doc_ref = db.collection(AI_ASSISTANT_CHATS_COLLECTION).document(chat_id)
    
    # Check if document exists
    doc_snapshot = doc_ref.get()
    now = int(time.time() * 1000)
    if doc_snapshot.exists:
        # Update existing document with atomic increment
        update_data = {
            "lastMessageAt": now,
            "updatedAt": now,
            "totalMessageCount": Increment(message_count),
            "lastMessage": last_message
        }
        doc_ref.update(update_data)
        
        # Return the updated data by getting the current values first
        current_data = doc_snapshot.to_dict()
        # Create a new dict for the response with manually calculated count
        response_data = current_data.copy()
        response_data["lastMessageAt"] = now
        response_data["updatedAt"] = now
        response_data["totalMessageCount"] = (current_data.get("totalMessageCount") or 0) + message_count
        return response_data
    else:
        # Create new document
        new_chat_data = {
            "id": chat_id,
            "userId": user_id,
            "createdAt": now,
            "lastMessageAt": now,
            "updatedAt": now,
            "totalMessageCount": message_count,
            "lastMessage": last_message,
            "title": title
        }
        doc_ref.set(new_chat_data)
        return new_chat_data
