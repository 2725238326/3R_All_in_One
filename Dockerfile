# Multi-stage build for 3R All-in-One
FROM python:3.11-slim as backend-builder

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python requirements
COPY requirements.txt /tmp/root-requirements.txt
COPY backend/requirements.txt /tmp/backend-requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /tmp/root-requirements.txt -r /tmp/backend-requirements.txt

# Expose backend port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DATA_ROOT=/app/data
ENV KYKT_DATA_ROOT=/app/data

# Create data directory
RUN mkdir -p /app/data

# Backend command
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

# Frontend stage
FROM node:18-alpine as frontend-builder

WORKDIR /app

# Copy frontend files
COPY client/package*.json ./

# Install dependencies
RUN npm ci

# Copy frontend source
COPY client/ .

# Build frontend
RUN npm run build

# Production stage
FROM python:3.11-slim

WORKDIR /app/backend

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from backend-builder
COPY --from=backend-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin

# Copy application resources in the layout expected by runtime_paths.py
COPY backend/ /app/backend/
COPY agent/ /app/agent/
COPY runners/ /app/runners/
COPY samples/ /app/samples/
COPY tools/ /app/tools/

# Copy frontend build from frontend-builder
COPY --from=frontend-builder /app/dist /app/client/dist

# Expose ports
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DATA_ROOT=/app/data
ENV KYKT_DATA_ROOT=/app/data
ENV PYTHONPATH=/app/backend:/app

# Create data directory
RUN mkdir -p /app/data

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Production command
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
