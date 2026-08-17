# No torch: EMBEDDING_PROVIDER=google (the default) needs only the lightweight
# google-genai client, which is what keeps this image to roughly 400MB instead
# of the ~2.5GB that sentence-transformers + torch would add. tree-sitter and
# tree-sitter-language-pack ship manylinux wheels, so no compiler is needed
# either - this stays a single stage.
FROM python:3.13-slim

RUN groupadd --system ragbot && useradd --system --gid ragbot --create-home ragbot

WORKDIR /app

# Dependencies first, so an app-code-only change doesn't invalidate this layer.
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY ragbot ./ragbot

ENV RAGBOT_DATA_DIR=/data \
    RAGBOT_LOG_DIR=/logs \
    PYTHONUNBUFFERED=1

RUN mkdir -p /data /logs && chown -R ragbot:ragbot /app /data /logs
USER ragbot

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=3)" || exit 1

CMD ["python", "-m", "uvicorn", "ragbot.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
