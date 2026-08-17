"""FastAPI app: CORS, lifespan-managed state, and route registration.

Run with: uvicorn ragbot.api.main:app --reload --app-dir backend
(or, inside the container, `python -m uvicorn ragbot.api.main:app` from /app).
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from ragbot.api.routes import chat, jobs, meta, repos
from ragbot.api.state import AppState

DEFAULT_CORS_ORIGINS = 'http://localhost:3000'


@asynccontextmanager
async def lifespan(app: FastAPI):
    # One AppState per process, hung off app.state rather than a module-level
    # global - see ragbot.api.state.get_state.
    app.state.ragbot = AppState()
    yield


app = FastAPI(title='RAGBot API', lifespan=lifespan)

origins = [o.strip() for o in os.getenv('CORS_ORIGINS', DEFAULT_CORS_ORIGINS).split(',') if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.include_router(meta.router, prefix='/api')
app.include_router(repos.router, prefix='/api')
app.include_router(jobs.router, prefix='/api')
app.include_router(chat.router, prefix='/api')
