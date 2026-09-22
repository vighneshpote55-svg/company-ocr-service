"""
chat_repository.py
Multi-turn AI Chat Repository with User and Document Isolation:
- Database source of truth: Supabase PostgreSQL (chat_sessions, chat_messages)
- Ensures chat history is strictly isolated by (user_id, document_id)
- User A cannot view or post messages to User B's document chat
- Local fallback when Supabase is unconfigured
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import logging_utils
from supabase_client import get_supabase_client, is_supabase_configured

logger = logging_utils.get_logger("company_server_ocr.chat_repository")

# In-memory fallback for local dev / tests when Supabase is not configured: (user_id, document_id) -> list of messages
_local_chat_store: Dict[str, List[Dict[str, Any]]] = {}


def _get_local_key(user_id: str, document_id: str) -> str:
    return f"{user_id}:{document_id}"


def get_or_create_session(
    user_id: str,
    document_id: str,
    provider: str,
    model: str
) -> str:
    """
    Retrieve existing active chat session ID for (user_id, document_id) or create a new one.
    """
    if is_supabase_configured():
        client = get_supabase_client()
        if client:
            try:
                res = client.table("chat_sessions").select("id").eq("user_id", user_id).eq("document_id", document_id).order("created_at", desc=True).limit(1).execute()
                if res.data and len(res.data) > 0:
                    return res.data[0]["id"]

                # Create new session
                session_id = str(uuid.uuid4())
                client.table("chat_sessions").insert({
                    "id": session_id,
                    "user_id": user_id,
                    "document_id": document_id,
                    "provider": provider,
                    "model": model,
                }).execute()
                return session_id
            except Exception as ex:
                logger.error(f"Failed to manage chat session in Supabase: {type(ex).__name__}")

    # Local fallback
    return f"session_{user_id}_{document_id}"


def add_chat_message(
    user_id: str,
    document_id: str,
    role: str,
    content: str,
    provider: str = "default",
    model: str = "default",
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Append a chat message to the user and document's conversation history.
    """
    msg_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    if is_supabase_configured():
        client = get_supabase_client()
        if client:
            try:
                if not session_id:
                    session_id = get_or_create_session(user_id, document_id, provider, model)

                msg_row = {
                    "id": msg_id,
                    "session_id": session_id,
                    "user_id": user_id,
                    "document_id": document_id,
                    "role": role,
                    "content": content,
                    "created_at": now_iso,
                }
                client.table("chat_messages").insert(msg_row).execute()
                return msg_row
            except Exception as ex:
                logger.error(f"Failed to save chat message in Supabase: {type(ex).__name__}")

    # Local fallback
    key = _get_local_key(user_id, document_id)
    if key not in _local_chat_store:
        _local_chat_store[key] = []
    entry = {
        "id": msg_id,
        "role": role,
        "content": content,
        "timestamp": now_iso,
        "created_at": now_iso,
    }
    _local_chat_store[key].append(entry)
    return entry


def get_chat_history(
    user_id: str,
    document_id: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Fetch chronological conversation history for (user_id, document_id).
    Strictly isolated: User A cannot see User B's conversation.
    """
    if is_supabase_configured():
        client = get_supabase_client()
        if client:
            try:
                res = client.table("chat_messages").select(
                    "id, role, content, created_at"
                ).eq("user_id", user_id).eq("document_id", document_id).order("created_at", desc=False).limit(limit).execute()

                history = []
                for row in res.data or []:
                    history.append({
                        "id": row.get("id"),
                        "role": row.get("role"),
                        "content": row.get("content"),
                        "timestamp": row.get("created_at"),
                    })
                return history
            except Exception as ex:
                logger.error(f"Failed to fetch chat history from Supabase: {type(ex).__name__}")

    # Local fallback
    key = _get_local_key(user_id, document_id)
    return _local_chat_store.get(key, [])
