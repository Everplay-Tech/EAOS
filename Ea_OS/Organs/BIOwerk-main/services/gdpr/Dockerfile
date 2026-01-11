FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy matrix shared library
COPY matrix /app/matrix/

# Copy service code
COPY services/gdpr /app/services/gdpr/

# Create GDPR exports directory
RUN mkdir -p /var/gdpr_exports && chmod 755 /var/gdpr_exports

# Expose port
EXPOSE 8010

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8010/health || exit 1

# Run the service
CMD ["python", "-m", "uvicorn", "services.gdpr.main:app", "--host", "0.0.0.0", "--port", "8010"]
