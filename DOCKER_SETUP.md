# COGNIS Docker Compose Setup Guide

This guide explains how to run the entire COGNIS stack using Docker Compose.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (20.10+)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2.0+)
- At least 8GB RAM (16GB recommended for Ollama)
- 50GB disk space (for Ollama models)

## Quick Start

### 1. Clone and Setup

```bash
cd /path/to/cognis
cp .env.example .env
# Edit .env with your configuration
```

### 2. Start All Services

```bash
docker-compose up -d
```

This will start:
- **PostgreSQL** (port 5432) - Main database
- **ChromaDB** (port 8000) - Vector database
- **Ollama** (port 11434) - LLM service
- **Backend** (port 8000) - FastAPI server
- **Frontend** (port 3000) - React app

### 3. Initialize Ollama Models

Once Ollama is running, pull the default model:

```bash
docker exec cognis-ollama ollama pull qwen2.5:7b
```

Or use a different model:

```bash
docker exec cognis-ollama ollama pull mistral:7b
docker exec cognis-ollama ollama pull neural-chat:7b
```

### 4. Verify Services

Check service status:

```bash
docker-compose ps
```

Access the services:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Swagger Docs: http://localhost:8000/docs
- ChromaDB: http://localhost:8000 (ChroaDB port, not same as docs)
- PostgreSQL: localhost:5432

## Configuration

### Environment Variables

Edit `.env` to customize:

```env
# Database credentials
POSTGRES_USER=cognis
POSTGRES_PASSWORD=your_secure_password

# Email service
RESEND_API_KEY=your_resend_api_key

# Ollama model selection
OLLAMA_MODEL=qwen2.5:7b

# Frontend URL
FRONTEND_URL=http://localhost:3000
```

### Port Configuration

Change ports by editing `.env`:

```env
POSTGRES_PORT=5433
CHROMA_PORT=8001
OLLAMA_PORT=11434
BACKEND_PORT=8001
FRONTEND_PORT=3001
```

## Database Migrations

Apply migrations automatically or manually:

```bash
# Automatic (on backend start)
docker-compose up backend

# Manual with alembic
docker exec cognis-backend alembic upgrade head
```

## Logs and Debugging

### View Logs

```bash
# All services
docker-compose logs

# Specific service
docker-compose logs backend
docker-compose logs frontend
docker-compose logs ollama

# Follow logs
docker-compose logs -f backend
```

### Check Service Health

```bash
# PostgreSQL
docker exec cognis-postgres pg_isready -U cognis

# ChromaDB
curl http://localhost:8000/api/version

# Ollama
curl http://localhost:11434/api/tags

# Backend
curl http://localhost:8000/docs
```

## Common Issues

### 1. Port Already in Use

If ports are already in use, update `.env` or stop conflicting services:

```bash
# Find what's using port 8000
lsof -i :8000
kill -9 <PID>
```

### 2. Ollama Out of Memory

Ollama needs ~7-8GB RAM per model. Free up memory:

```bash
docker system prune -a
# Or reduce model size
docker exec cognis-ollama ollama pull mistral:7b  # Smaller model
```

### 3. Database Connection Failed

Wait for PostgreSQL to be healthy:

```bash
docker-compose up postgres
# Wait 30 seconds for PostgreSQL to initialize
docker-compose up -d
```

### 4. ChromaDB Won't Start

Ensure /var/lib/docker/volumes has enough space:

```bash
docker system df
docker system prune -a
```

## Useful Commands

### Stop All Services

```bash
docker-compose down
```

### Stop and Remove Data

```bash
docker-compose down -v
```

### Rebuild Images

```bash
docker-compose build --no-cache
docker-compose up -d
```

### Run Database Migrations

```bash
docker exec cognis-backend alembic upgrade head
```

### Access PostgreSQL Shell

```bash
docker exec -it cognis-postgres psql -U cognis -d cognis_db
```

### Ollama Model Management

```bash
# List all models
docker exec cognis-ollama ollama list

# Pull a model
docker exec cognis-ollama ollama pull llama2:7b

# Remove a model
docker exec cognis-ollama ollama rm qwen2.5:7b
```

### Restart a Service

```bash
docker-compose restart backend
docker-compose restart frontend
```

### Backend Shell

```bash
docker exec -it cognis-backend bash
```

## Production Deployment

### Update for Production

1. Update `.env` with production values:

```env
DEBUG=false
ENVIRONMENT=production
SECRET_KEY=your-random-secure-key-min-32-chars
```

2. Use environment-specific docker-compose:

```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

3. Setup SSL/HTTPS (use Nginx or Let's Encrypt)

4. Use external database (instead of local PostgreSQL)

5. Setup email service credentials (RESEND_API_KEY)

## Monitoring

### Resource Usage

```bash
docker stats
```

### Database Statistics

```bash
docker exec cognis-postgres psql -U cognis -d cognis_db -c "SELECT datname, pg_size_pretty(pg_database_size(datname)) FROM pg_database;"
```

### Ollama Model Info

```bash
docker exec cognis-ollama ollama show qwen2.5:7b
```

## Backup and Restore

### Backup Database

```bash
docker exec cognis-postgres pg_dump -U cognis cognis_db > backup.sql
```

### Restore Database

```bash
docker exec -i cognis-postgres psql -U cognis cognis_db < backup.sql
```

### Backup Volumes

```bash
docker run --rm -v cognis_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz -C /data .
```

## Performance Tuning

### PostgreSQL

Add to docker-compose.yml environment:

```yaml
POSTGRES_INIT_ARGS: "-c shared_buffers=256MB -c max_connections=200"
```

### Ollama

Adjust Ollama context window (memory usage):

```bash
docker exec cognis-ollama ollama run qwen2.5:7b /set parameter num_ctx 2048
```

## GPU Support (Advanced)

For NVIDIA GPU support with Ollama:

1. Install [nvidia-docker](https://github.com/NVIDIA/nvidia-docker)

2. Update docker-compose.yml:

```yaml
ollama:
  image: ollama/ollama:latest-gpu  # Use GPU image
  runtime: nvidia
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

3. Start services:

```bash
docker-compose up -d
```

## Support and Troubleshooting

For issues:

1. Check logs: `docker-compose logs -f`
2. Verify health: `docker-compose ps`
3. Restart services: `docker-compose restart`
4. Clean and rebuild: `docker-compose down -v && docker-compose build --no-cache && docker-compose up -d`

## Next Steps

After startup:

1. Navigate to http://localhost:3000
2. Create an account
3. Upload your resume
4. Set job search criteria
5. View the API docs at http://localhost:8000/docs
