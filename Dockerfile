# --- Stage 1: Build the React Frontend ---
FROM node:18-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm install

COPY frontend/ .
# Inject VITE_API_URL during build. In single-container mode, we want requests to go to the same host/port.
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# --- Stage 2: Build the FastAPI Backend & Assemble ---
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies needed for PyMuPDF, Playwright, and cryptography packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    librandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Install python requirements
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model at build time
RUN python -m spacy download en_core_web_sm

# Install playwright browsers at build time
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy backend application source
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini .

# Copy built frontend assets to uvicorn static directory
COPY --from=frontend-builder /app/frontend/dist ./static

EXPOSE 8000

# Set environment to serve static files
ENV SERVE_STATIC_FRONTEND=true

# Use uvicorn to run the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
