FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN pip install requests uv
RUN uv export > requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000', timeout=10)" || exit 1

EXPOSE 8000

CMD ["python", "-m", "src.main", "--http"]