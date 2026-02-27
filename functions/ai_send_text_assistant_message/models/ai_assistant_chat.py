from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Literal

RoleType = Literal["user", "assistant"]

@dataclass
class AiAssistantMessage:
    id: str                           # Unique message ID
    role: RoleType                    # 'user' or 'assistant'
    content: str                       # Message text (input/output unified here)
    summarized: Optional[bool] = None
    rate: int = 0
    tokenUsage: Optional[dict] = None
    event: str = None
    eventData: Optional[dict] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    attachments: Optional[List[dict]] = field(default_factory=list)
    isCxInteraction: bool = False

@dataclass
class AiAssistantChat:
    id: str                           # Unique conversation/session ID
    userId: str                       # User who owns the conversation
    lastMessageAt: Optional[str] = None
    createdAt: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updatedAt: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    totalMessageCount: int = 0

