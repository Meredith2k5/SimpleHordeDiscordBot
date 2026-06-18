FROM python:3.11-slim

WORKDIR /app

# Create the data directory (logs will be created inside this by Python)
RUN mkdir -p /data

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run as non-root for security
RUN useradd -m appuser && chown -R appuser:appuser /app && chown -R appuser:appuser /data
USER appuser

CMD ["python", "main.py"]