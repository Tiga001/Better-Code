from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class MessageRole(str, Enum):
    """Role of a message in a conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

class Message(BaseModel):
    """Standard message structure for LLM conversations."""
    role: MessageRole      # Role of the message (system, user, assistant, tool)
    content: str           # Text content of the message
    name: Optional[str] = None  # Optional name for tool/function calls

class TokenUsage(BaseModel):
    """Token consumption statistics."""
    prompt_tokens: int = 0       # Number of tokens in the input prompt
    completion_tokens: int = 0   # Number of tokens in the completion
    total_tokens: int = 0        # Total tokens consumed

class LLMResponse(BaseModel):
    """Unified response model for non-streaming LLM calls."""
    content: str                              # The generated text content
    model: str                                # Actual model identifier used
    usage: TokenUsage = Field(default_factory=TokenUsage)  # Token usage statistics
    latency_ms: int = 0                       # Request latency in milliseconds
    reasoning_content: Optional[str] = None   # Reasoning/thinking content (for reasoning models like o1, deepseek-reasoner)

class StreamChunk(BaseModel):
    """Unified chunk model for streaming LLM responses."""
    content: str = ""                         # Chunk of the main content
    reasoning_content: str = ""               # Chunk of reasoning content (if any)
    is_finished: bool = False                 # Whether this is the final chunk
    usage: Optional[TokenUsage] = None        # Final token usage (usually provided in the last chunk)