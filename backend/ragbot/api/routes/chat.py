import json

import anyio
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from ragbot.api.schemas import (
    AskRequest,
    ConversationCreate,
    ConversationCreated,
    ConversationDetail,
    MessageOut,
)
from ragbot.api.state import AppState, get_state, read_repo_meta

router = APIRouter(prefix='/conversations', tags=['conversations'])


def _to_detail(conv: dict) -> ConversationDetail:
    return ConversationDetail(
        id=conv['id'], repo_key=conv['repo_key'], created_at=conv['created_at'],
        messages=[MessageOut(**m) for m in conv['messages']],
    )


@router.post('', response_model=ConversationCreated, status_code=201)
def create_conversation(payload: ConversationCreate, state: AppState = Depends(get_state)) -> ConversationCreated:
    meta = read_repo_meta(payload.repo_key)
    if meta is None:
        raise HTTPException(404, f"No cached repo '{payload.repo_key}'.")
    if not meta.get('chunking_strategy'):
        raise HTTPException(409, f"Repo '{payload.repo_key}' has not finished ingesting yet.")

    conv_id = state.conversations.create(payload.repo_key)
    return ConversationCreated(conversation_id=conv_id, repo_key=payload.repo_key)


@router.get('/{conversation_id}', response_model=ConversationDetail)
def get_conversation(conversation_id: str, state: AppState = Depends(get_state)) -> ConversationDetail:
    conv = state.conversations.get(conversation_id)
    if conv is None:
        raise HTTPException(404, f"No conversation '{conversation_id}'.")
    return _to_detail(conv)


@router.delete('/{conversation_id}', status_code=204)
def clear_conversation(conversation_id: str, state: AppState = Depends(get_state)) -> None:
    if not state.conversations.clear(conversation_id):
        raise HTTPException(404, f"No conversation '{conversation_id}'.")


@router.post('/{conversation_id}/messages')
async def ask(conversation_id: str, payload: AskRequest, state: AppState = Depends(get_state)):
    conv = state.conversations.get(conversation_id)
    if conv is None:
        raise HTTPException(404, f"No conversation '{conversation_id}'.")

    try:
        built = await anyio.to_thread.run_sync(state.get_or_build_index, conv['repo_key'])
    except KeyError as e:
        raise HTTPException(409, str(e))

    async def generate():
        full_text = ''
        citations = []
        history_sink: list = []
        try:
            async for event in built.agent_wrapper.run_stream(
                payload.content, message_history=conv['pydantic_ai_history'], history_sink=history_sink,
            ):
                if event['event'] == 'token':
                    full_text += event['data']['delta']
                elif event['event'] == 'citation':
                    citations.append(event['data'])
                yield {'event': event['event'], 'data': json.dumps(event['data'])}
        except Exception as e:
            yield {'event': 'error', 'data': json.dumps({'detail': str(e)})}
            return

        new_history = history_sink[0] if history_sink else conv['pydantic_ai_history']
        state.conversations.append_turn(
            conversation_id,
            question=payload.content,
            answer=full_text,
            citations=citations,
            history=new_history,
        )

    return EventSourceResponse(generate())
