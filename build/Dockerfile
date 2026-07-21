FROM python:3.13-slim AS deps

WORKDIR /app

# requirements.txt is generated from pyproject.toml + uv.lock so dependencies have
# a single source of truth and cannot drift against a hand-maintained lockfile.
RUN pip install --no-cache-dir uv==0.10.4

COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project -o requirements.txt \
    && pip install --no-cache-dir -r requirements.txt

FROM python:3.13-slim AS runtime

WORKDIR /app

# Copy installed packages from the deps stage
COPY --from=deps /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

COPY src/ src/
COPY tests/ tests/

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=10)" || exit 1

EXPOSE 8000

CMD ["python", "-m", "src.main", "--http"]
