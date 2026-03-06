# Use the official Python lightweight image
FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .
# Allow statements and log messages to immediately appear in the logs
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "mcp_client:app", "--host", "0.0.0.0", "--port", "8080"]