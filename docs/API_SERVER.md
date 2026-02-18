# REST API Server

Complete guide to NeoFlow's REST API for programmatic access and integrations.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Authentication](#authentication)
- [Endpoints](#endpoints)
- [Session Management](#session-management)
- [Error Handling](#error-handling)
- [Examples](#examples)

## Overview

NeoFlow provides a production-ready REST API built with FastAPI, offering both stateless queries and stateful session-based conversations.

### Features

- **Stateless Queries**: Single-request Q&A
- **Session Management**: Multi-turn conversations
- **Template System**: Reusable query templates
- **Health Monitoring**: Service status checks
- **CORS Support**: Configurable cross-origin access
- **Auto Documentation**: Swagger UI and ReDoc
- **Async**: High-performance async endpoints

## Quick Start

### Start Server

```bash
# Default (localhost:9720)
neoflow serve

# Custom host and port
neoflow serve --host 0.0.0.0 --port 8000

# Development mode with auto-reload
neoflow serve --reload
```

### Test Connection

```bash
curl http://localhost:9720/api/v1/health
```

### Interactive Documentation

- Swagger UI: http://localhost:9720/docs
- ReDoc: http://localhost:9720/redoc

## Authentication

Currently, the API does not require authentication. For production deployments, consider adding:

- API key authentication via middleware
- OAuth2/JWT for user-based access
- IP whitelisting
- Rate limiting

## Endpoints

### Health Check

Check service status.

**Endpoint:** `GET /api/v1/health`

**Response:**
```json
{
  "status": "healthy",
  "services": {
    "weaviate": "connected",
    "llm": "ollama",
    "version": "0.0.21"
  }
}
```

### Query (Stateless)

Execute single query without session.

**Endpoint:** `POST /api/v1/query`

**Request:**
```json
{
  "query": "How do I implement JWT authentication?",
  "max_iterations": 25
}
```

**Response:**
```json
{
  "answer": "To implement JWT authentication...",
  "sources": [
    "backend/auth_service.py",
    "docs/authentication.md"
  ],
  "iterations_used": 8
}
```

### Create Session

Start new conversation session.

**Endpoint:** `POST /api/v1/sessions`

**Request:**
```json
{
  "initial_message": "I need help with authentication"
}
```

**Response:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2024-02-17T10:30:00Z",
  "expires_at": "2024-02-17T11:30:00Z"
}
```

### Get Session

Retrieve session information.

**Endpoint:** `GET /api/v1/sessions/{session_id}`

**Response:**
```json
{
  "session_id": "550e8400...",
  "created_at": "2024-02-17T10:30:00Z",
  "last_accessed": "2024-02-17T10:35:00Z",
  "message_count": 4,
  "expires_at": "2024-02-17T11:30:00Z"
}
```

### Send Message to Session

Continue conversation in existing session.

**Endpoint:** `POST /api/v1/sessions/{session_id}/messages`

**Request:**
```json
{
  "message": "Show me an example implementation"
}
```

**Response:**
```json
{
  "answer": "Here's an example from our codebase...",
  "sources": ["backend/auth_service.py"],
  "message_count": 5
}
```

### Get Session History

Retrieve conversation history.

**Endpoint:** `GET /api/v1/sessions/{session_id}/history`

**Response:**
```json
{
  "session_id": "550e8400...",
  "messages": [
    {
      "role": "user",
      "content": "I need help with authentication",
      "timestamp": "2024-02-17T10:30:00Z"
    },
    {
      "role": "assistant",
      "content": "I can help with that...",
      "timestamp": "2024-02-17T10:30:15Z"
    }
  ]
}
```

### Delete Session

End session and cleanup.

**Endpoint:** `DELETE /api/v1/sessions/{session_id}`

**Response:**
```json
{
  "message": "Session deleted successfully"
}
```

### List Templates

Get available query templates.

**Endpoint:** `GET /api/v1/templates`

**Response:**
```json
{
  "templates": [
    {
      "name": "sow",
      "title": "Statement of Work",
      "fields": ["project_name", "description", "scope"]
    },
    {
      "name": "status",
      "title": "Status Report",
      "fields": ["project", "progress", "issues"]
    }
  ]
}
```

### Use Template

Execute query using template.

**Endpoint:** `POST /api/v1/templates/{template_name}`

**Request:**
```json
{
  "values": {
    "project_name": "User Management API",
    "description": "REST API for user CRUD operations",
    "scope": "Backend development only"
  }
}
```

**Response:**
```json
{
  "answer": "Based on your requirements...",
  "sources": ["docs/api_patterns.md"]
}
```

## Session Management

Sessions maintain conversation context across multiple requests.

### Lifestyle

1. **Create**: `POST /api/v1/sessions`
2. **Use**: `POST /api/v1/sessions/{id}/messages` (multiple times)
3. **Expire**: Automatic after TTL or manual `DELETE`

### Configuration

```python
@dataclass
class ServerConfig:
    session_ttl_minutes: int = 60  # Session lifetime
    max_sessions: int = 100         # Max concurrent sessions
```

### Cleanup

- Automatic cleanup task runs every minute
- Removes expired sessions
- Saves history (if enabled)

## Error Handling

### Standard Error Response

```json
{
  "error": "SessionNotFound",
  "message": "Session 550e8400... not found or expired",
  "status_code": 404
}
```

### Error Codes

| Code | Error | Description |
|------|-------|-------------|
| 400 | BadRequest | Invalid request parameters |
| 404 | NotFound | Session or resource not found |
| 409 | Conflict | Session limit reached |
| 422 | ValidationError | Request validation failed |
| 500 | InternalError | Server error |
| 503 | ServiceUnavailable | Weaviate/LLM unavailable |

## Examples

### Example 1: Simple Query

```bash
curl -X POST http://localhost:9720/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How to configure CORS in FastAPI?"
  }'
```

### Example 2: Session-Based Conversation

```python
import requests

BASE_URL = "http://localhost:9720/api/v1"

# Create session
response = requests.post(f"{BASE_URL}/sessions", json={
    "initial_message": "Tell me about authentication"
})
session_id = response.json()["session_id"]

# Continue conversation
response = requests.post(
    f"{BASE_URL}/sessions/{session_id}/messages",
    json={"message": "Show me code examples"}
)
print(response.json()["answer"])

# Get history
response = requests.get(f"{BASE_URL}/sessions/{session_id}/history")
print(response.json()["messages"])

# Cleanup
requests.delete(f"{BASE_URL}/sessions/{session_id}")
```

### Example 3: Using Templates

```bash
curl -X POST http://localhost:9720/api/v1/templates/sow \
  -H "Content-Type: application/json" \
  -d '{
    "values": {
      "project_name": "Payment Gateway",
      "description": "Integrate Stripe payments",
      "scope": "Backend and API only"
    }
  }'
```

### Example 4: Health Monitoring

```python
import requests
from time import sleep

def check_health():
    try:
        response = requests.get(
            "http://localhost:9720/api/v1/health",
            timeout=5
        )
        return response.status_code == 200
    except:
        return False

while True:
    if not check_health():
        print("Service unhealthy!")
        # Alert or restart
    sleep(60)
```

## See Also

- [CLI Reference](CLI_REFERENCE.md)
- [Chat System](CHAT_SYSTEM.md)
- [Configuration](CONFIGURATION.md)
