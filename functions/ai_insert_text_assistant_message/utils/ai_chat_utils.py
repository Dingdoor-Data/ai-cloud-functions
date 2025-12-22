import datetime
import time
from google.cloud.firestore import Increment
from datetime import datetime
AI_ASSISTANT_CHATS = "aiAssistantChats"

def update_chat_metadata(db, chat_id, last_message, message_count=1):
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
    doc_ref = db.collection(AI_ASSISTANT_CHATS).document(chat_id)
    
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

def save_messages_to_firestore(db,messages_collection,role, user_message_ref,msg_id,user_message, user_timestamp,event,event_data,attachments=None):
    """
    Save user message to Firestore
    in messages/{chatId}/messages/ collection
    """
    # Create user message
    user_message_data = {
        "role":role,
        "content":user_message if user_message else "",
        "timestamp":user_timestamp,
        "id":msg_id, 
        "attachments":attachments or [],
        "event":event or None,
        "eventData":event_data or {},
        "isCxInteraction":True,
        "rate":0,
    }
    
    # Use a batch write for efficiency
    batch = db.batch()
    batch.set(user_message_ref, user_message_data)
    batch.commit()

    return user_message_data