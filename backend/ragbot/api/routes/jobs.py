import json

import anyio
from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from ragbot.api.schemas import JobStatus
from ragbot.api.state import AppState, get_state

router = APIRouter(prefix='/jobs', tags=['jobs'])

TERMINAL_STATUSES = {'succeeded', 'failed'}
POLL_INTERVAL_SECONDS = 0.3


def _to_job_status(job: dict) -> JobStatus:
    return JobStatus(
        id=job['id'], kind=job['kind'], status=job['status'], phase=job['phase'],
        message=job['message'], error=job['error'], result=job['result'], created_at=job['created_at'],
    )


@router.get('/{job_id}', response_model=JobStatus)
def get_job(job_id: str, state: AppState = Depends(get_state)) -> JobStatus:
    job = state.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, f"No job '{job_id}'.")
    return _to_job_status(job)


@router.get('/{job_id}/events')
async def job_events(job_id: str, state: AppState = Depends(get_state)):
    if state.jobs.get(job_id) is None:
        raise HTTPException(404, f"No job '{job_id}'.")

    async def generate():
        last_version = -1
        while True:
            job = state.jobs.get(job_id)
            if job is None:
                break

            if job['version'] != last_version:
                last_version = job['version']
                yield {'event': 'status', 'data': json.dumps(_to_job_status(job).model_dump())}

            if job['status'] in TERMINAL_STATUSES:
                break

            await anyio.sleep(POLL_INTERVAL_SECONDS)

    return EventSourceResponse(generate())
