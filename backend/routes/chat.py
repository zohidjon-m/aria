import json
import logging
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
from backend.models import ChatRequest

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/chat")
async def chat_endpoint(request: ChatRequest, req: Request):
    agent = req.app.state.agent

    context_msg = ""
    if request.context:
        if "customer_id" in request.context:
            context_msg = f"The officer is currently viewing customer {request.context['customer_id']}."
        elif "alert_id" in request.context:
            context_msg = f"The officer is currently viewing alert {request.context['alert_id']}."
        elif "case_id" in request.context:
            context_msg = f"The officer is currently viewing case {request.context['case_id']}."

    async def generate():
        try:
            async for chunk in agent.chat(request.message, request.history, context_msg):
                yield {"event": "message", "data": json.dumps(chunk)}
        except Exception as e:
            logger.error("Agent error during chat: %s", e, exc_info=True)
            error_chunk = {
                "type": "content_block_delta",
                "delta": {"text": f"\n\n[Error: {str(e)}]"},
            }
            yield {"event": "message", "data": json.dumps(error_chunk)}
            yield {"event": "message", "data": json.dumps({"type": "message_stop"})}

    return EventSourceResponse(generate())
