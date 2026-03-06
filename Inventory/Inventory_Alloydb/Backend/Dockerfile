# Use an official Python base image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Set environment variables if needed (optional)
# ENV GOOGLE_APPLICATION_CREDENTIALS=/app/key.json
COPY key.json /app/inventory-management-app/key.json

# Expose the port FastAPI will run on
EXPOSE 8080

# Run the FastAPI app using uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]