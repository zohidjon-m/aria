from pydantic import BaseModel
from typing import Optional, List

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []
    context: Optional[dict] = None  # current customer/alert/case in view

class ChatResponse(BaseModel):
    message: str
    tool_calls: List[dict] = []
