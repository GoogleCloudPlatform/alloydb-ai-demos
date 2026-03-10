FROM python:3.12-slim-bookworm

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .


# Expose the port that FastAPI will listen on
EXPOSE 8080

# Set environment variables
ENV PORT=8080

# Command to run the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]