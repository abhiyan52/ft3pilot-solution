FROM python:3.12-slim
WORKDIR /app
COPY . .
# Editable, so the case schema, the model routes, and migrations stay beside the code that reads them.
# C1-2: install the pinned versions of deploy/requirements.lock first, then the Solution itself. The freeze records what was installed.
RUN pip install --no-cache-dir -r deploy/requirements.lock && pip install --no-cache-dir --no-deps -e . && pip freeze > /app/deploy/tool-versions-resolved.txt
# Run as a user without privileges. The image holds no secret, but a process needs no root.
RUN useradd --system --create-home --uid 10001 app && chown -R app:app /app
USER app
# Apply the database migrations, then serve. A migration that fails stops the container.
CMD ["sh", "-c", "python -c 'from solution import db; db.migrate()' && exec uvicorn solution.api:app --host 0.0.0.0 --port 8000"]
