FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements-mock.txt .
RUN pip install --no-cache-dir -r requirements-mock.txt

# Copy the mock service
COPY google_api_mock/mock_google_api.py .

# Create a health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost/health', timeout=10)" || exit 1

# Expose the port the mock service runs on
EXPOSE 80

# Run the mock service
CMD ["uvicorn", "mock_google_api:app", "--host", "0.0.0.0", "--port", "80"]