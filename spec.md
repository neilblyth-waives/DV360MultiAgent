# DV360 Multi-Agent System - Technical Specification

**Version:** 0.1.0
**Last Updated:** 2024-01-12
**Status:** Sprint 2 - 50% Complete

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Technology Stack](#technology-stack)
4. [Database Schema](#database-schema)
5. [Core Components](#core-components)
6. [Agent Framework](#agent-framework)
7. [Memory System](#memory-system)
8. [Tools & Integrations](#tools--integrations)
9. [API Specification](#api-specification)
10. [Deployment](#deployment)
11. [Implementation Status](#implementation-status)
12. [Future Roadmap](#future-roadmap)

---

## Project Overview

### Vision

An AI-powered DV360 strategy and analysis platform that provides intelligent, context-aware insights and recommendations through a multi-agent system. The system maintains growing intelligence through persistent memory across sessions, enabling continuous improvement and personalized analysis.

### Key Objectives

1. **Read-Only Analysis**: Analyze DV360 data from Snowflake and provide recommendations
2. **Multi-Agent Architecture**: Specialized agents for different DV360 domains
3. **Persistent Memory**: Learn and remember insights across sessions
4. **Production-Ready**: Scalable, observable, and production-grade from day one
5. **Session Continuity**: Continue conversations across multiple sessions

### Use Cases

- **Campaign Performance Analysis**: "How is campaign X performing?"
- **Budget Optimization**: "Is my budget pacing correctly?"
- **Audience Insights**: "Which audience segments are performing best?"
- **Creative Recommendations**: "What creative formats should I use?"
- **Strategic Planning**: "What should I do to improve ROAS?"

---

## Architecture

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Client Applications                   │
│              (Web UI, API Clients, CLI)                  │
└────────────────────────┬────────────────────────────────┘
                         │
                         │ HTTPS/WSS
                         ▼
┌─────────────────────────────────────────────────────────┐
│                    Load Balancer (Nginx)                 │
│              Rate Limiting, SSL Termination              │
└────────────────────────┬────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │ Backend │    │ Backend │    │ Backend │
    │ Replica │    │ Replica │    │ Replica │
    │    1    │    │    2    │    │    N    │
    └────┬────┘    └────┬────┘    └────┬────┘
         │              │              │
         └──────────────┼──────────────┘
                        │
         ┌──────────────┼──────────────┐
         │              │              │
         ▼              ▼              ▼
    ┌─────────┐  ┌──────────┐  ┌──────────┐
    │ PostgreSQL│  │  Redis   │  │Snowflake │
    │ +pgvector│  │  Cache   │  │(Read-Only)│
    └─────────┘  └──────────┘  └──────────┘
```

### Agent Architecture

```
                 ┌────────────────────────┐
                 │  Chat Conductor Agent  │
                 │   (Supervisor Pattern)  │
                 └──────────┬─────────────┘
                            │
        ┌──────────┬────────┴─────────┬──────────┐
        │          │                  │          │
┌───────▼──────┐ ┌▼─────────┐ ┌──────▼─────┐ ┌──▼──────────┐
│ Performance  │ │ Budget & │ │ Audience & │ │ Creative &  │
│ Diagnosis    │ │ Pacing   │ │ Targeting  │ │ Inventory   │
│ Agent        │ │ Agent    │ │ Agent      │ │ Agent       │
└──────────────┘ └──────────┘ └────────────┘ └─────────────┘
        │          │                  │          │
        └──────────┴──────────────────┴──────────┘
                            │
         ┌──────────────────┼──────────────────┐
         │                  │                  │
         ▼                  ▼                  ▼
  ┌────────────┐    ┌────────────┐    ┌────────────┐
  │ Snowflake  │    │   Memory   │    │  Decision  │
  │    Tool    │    │ Retrieval  │    │   Logger   │
  └────────────┘    └────────────┘    └────────────┘
```

### Data Flow

```
1. User sends message via API
      ↓
2. Session Manager creates/retrieves session
      ↓
3. Chat Conductor Agent receives message
      ↓
4. Conductor routes to specialist agent(s)
      ↓
5. Specialist agent:
   - Retrieves relevant memories (semantic search)
   - Executes tools (Snowflake queries)
   - Generates analysis
   - Logs decision
      ↓
6. Conductor aggregates responses
      ↓
7. New learnings extracted and stored (embeddings)
      ↓
8. Response returned to user
      ↓
9. Message history stored in session
```

---

## Technology Stack

### Backend Framework
- **Language**: Python 3.11+
- **Framework**: FastAPI (async web framework)
- **Server**: Uvicorn with multiple workers

### Agent Framework
- **LangChain**: LLM orchestration and tooling
- **LangGraph**: Multi-agent state management
- **OpenAI**: GPT-4 Turbo for reasoning + embeddings
- **Anthropic**: Claude 3 Opus (alternative LLM)

### Data & Storage
- **PostgreSQL 16**: Primary database
- **pgvector**: Vector similarity search (embeddings)
- **Redis 7**: Session cache, rate limiting, query cache
- **Snowflake**: DV360 data source (read-only)

### Observability
- **structlog**: Structured logging
- **Prometheus**: Metrics collection
- **Grafana**: Metrics visualization
- **OpenTelemetry**: Distributed tracing (optional)
- **LangSmith**: Agent debugging (optional)

### Deployment
- **Docker**: Containerization
- **Docker Compose**: Local development & testing
- **Kubernetes**: Production deployment (ready)
- **Nginx**: Load balancing & reverse proxy

### Development
- **Alembic**: Database migrations
- **pytest**: Testing framework
- **Locust**: Load testing
- **black**: Code formatting
- **ruff**: Linting

---

## Database Schema

### Tables

#### `sessions`
Stores conversation sessions.

```sql
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,

    INDEX idx_sessions_user_created (user_id, created_at)
);
```

#### `messages`
Stores all messages in conversations.

```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,  -- 'user', 'assistant', 'agent'
    content TEXT NOT NULL,
    agent_name VARCHAR(100),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,

    INDEX idx_messages_session_timestamp (session_id, timestamp)
);
```

#### `agent_decisions`
Audit trail of all agent decisions.

```sql
CREATE TABLE agent_decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    message_id UUID REFERENCES messages(id) ON DELETE CASCADE,
    agent_name VARCHAR(100) NOT NULL,
    decision_type VARCHAR(100) NOT NULL,
    input_data JSONB NOT NULL,
    output_data JSONB NOT NULL,
    tools_used JSONB,
    reasoning TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    execution_time_ms INTEGER,

    INDEX idx_decisions_agent_timestamp (agent_name, timestamp)
);
```

#### `agent_learnings`
Semantic memory store with vector embeddings.

```sql
CREATE TABLE agent_learnings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    content TEXT NOT NULL,
    embedding vector(1536),  -- OpenAI text-embedding-3-small
    source_session_id UUID REFERENCES sessions(id) ON DELETE SET NULL,
    agent_name VARCHAR(100) NOT NULL,
    learning_type VARCHAR(100) NOT NULL,  -- 'pattern', 'insight', 'rule', 'preference'
    confidence_score FLOAT NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB,

    INDEX idx_learnings_agent_created (agent_name, created_at),
    INDEX idx_learnings_type_confidence (learning_type, confidence_score)
);

-- Vector similarity search index
CREATE INDEX agent_learnings_embedding_idx
ON agent_learnings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

#### `query_cache`
Cache for Snowflake query results.

```sql
CREATE TABLE query_cache (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_hash VARCHAR(64) UNIQUE NOT NULL,
    query_text TEXT NOT NULL,
    result JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,

    INDEX idx_query_cache_expires (expires_at)
);
```

---

## Core Components

### Configuration Management

**File**: `backend/src/core/config.py`

Centralized configuration using Pydantic Settings:

```python
class Settings(BaseSettings):
    # Environment
    environment: str = "development"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # LLM
    openai_api_key: Optional[str]
    openai_model: str = "gpt-4-turbo-preview"
    anthropic_api_key: Optional[str]

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: str  # Auto-generated

    # Redis
    redis_host: str = "localhost"
    redis_url: str  # Auto-generated

    # Snowflake
    snowflake_account: str
    snowflake_user: str
    snowflake_password: str

    # Memory
    vector_dimension: int = 1536
    memory_top_k: int = 5

    # Rate Limiting
    rate_limit_requests_per_minute: int = 60
    rate_limit_tokens_per_day: int = 100000
```

### Database Management

**File**: `backend/src/core/database.py`

Async PostgreSQL with connection pooling:

```python
# SQLAlchemy async engine
engine = create_async_engine(
    database_url,
    pool_size=20,
    max_overflow=10,
)

# Raw asyncpg pool for vector operations
pg_pool = await asyncpg.create_pool(
    database_url,
    min_size=5,
    max_size=20,
)

# Usage
async with get_session() as session:
    # SQLAlchemy operations

async with get_pg_connection() as conn:
    # Raw SQL with pgvector
```

### Cache Management

**File**: `backend/src/core/cache.py`

Redis operations for caching and rate limiting:

```python
# Session management
await set_session(session_id, data, ttl_hours=24)
session_data = await get_session(session_id)

# Query caching
await set_query_cache(query_hash, results, ttl_minutes=60)
cached = await get_query_cache(query_hash)

# Rate limiting
is_allowed = await check_rate_limit(user_id, limit=60)
tokens_used = await increment_token_usage(user_id, tokens=100)

# Working memory
await set_working_memory(user_id, context)
context = await get_working_memory(user_id)
```

### Telemetry & Logging

**File**: `backend/src/core/telemetry.py`

Structured logging and Prometheus metrics:

```python
# Logging
logger = get_logger(__name__)
logger.info("Event occurred", key="value")

# Correlation IDs
set_correlation_id(correlation_id)
current_id = get_correlation_id()

# Metrics helpers
log_agent_execution(
    agent_name="performance_diagnosis",
    duration_seconds=1.5,
    status="success",
    tools_used=["snowflake_query"]
)

log_llm_request(
    provider="openai",
    model="gpt-4-turbo",
    duration_seconds=2.0,
    input_tokens=500,
    output_tokens=200
)
```

---

## Agent Framework

### Base Agent Class

**File**: `backend/src/agents/base.py`

All agents inherit from `BaseAgent`:

```python
class BaseAgent(ABC):
    def __init__(self, agent_name: str, description: str, tools: List[Any]):
        self.agent_name = agent_name
        self.description = description
        self.tools = tools
        self.llm = self._initialize_llm()

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return agent-specific system prompt"""
        pass

    @abstractmethod
    async def process(self, input_data: AgentInput) -> AgentOutput:
        """Process input and return output"""
        pass

    async def invoke(self, input_data: AgentInput) -> AgentOutput:
        """Main entry point - includes logging and error handling"""
        pass

    def build_graph(self) -> StateGraph:
        """Build LangGraph state graph"""
        pass
```

### Creating a New Agent

```python
from ..agents.base import BaseAgent
from ..schemas.agent import AgentInput, AgentOutput

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_name="my_agent",
            description="What this agent does",
            tools=[tool1, tool2]
        )

    def get_system_prompt(self) -> str:
        return """
        You are a specialized agent that...

        Available tools:
        - tool1: Description
        - tool2: Description

        Always provide detailed reasoning.
        """

    async def process(self, input_data: AgentInput) -> AgentOutput:
        # 1. Get relevant memories
        memories = await vector_store.search_similar(
            query=input_data.message,
            agent_name=self.agent_name
        )

        # 2. Build context
        context = self._build_context(input_data, memories)

        # 3. Use LLM with tools
        response = await self.llm.ainvoke(
            [
                SystemMessage(content=self.get_system_prompt()),
                HumanMessage(content=f"{context}\n\nUser: {input_data.message}")
            ]
        )

        # 4. Extract learnings
        if should_store_learning(response):
            await vector_store.store_learning(...)

        # 5. Return output
        return AgentOutput(
            response=response.content,
            agent_name=self.agent_name,
            reasoning="...",
            tools_used=["tool1"],
        )
```

### Agent Specifications

#### Performance Diagnosis Agent
**Status**: Not yet implemented
**Purpose**: Analyze campaign performance and provide insights

**Capabilities**:
- Query campaign metrics from Snowflake
- Compare performance against historical data
- Identify trends and anomalies
- Provide actionable recommendations

**Tools**:
- Snowflake query tool
- Memory retrieval
- Seasonality context

#### Budget & Pacing Agent
**Status**: Not yet implemented
**Purpose**: Monitor budget pacing and spending

**Capabilities**:
- Calculate pacing percentages
- Project end-of-period spend
- Alert on over/under-pacing
- Recommend budget adjustments

#### Audience & Targeting Agent
**Status**: Not yet implemented
**Purpose**: Analyze audience segment performance

**Capabilities**:
- Compare segment performance
- Identify high-performing audiences
- Recommend targeting changes
- Analyze demographic trends

#### Creative & Inventory Agent
**Status**: Not yet implemented
**Purpose**: Analyze creative and inventory performance

**Capabilities**:
- Compare creative performance
- Identify winning formats
- Recommend creative optimizations
- Analyze inventory sources

#### Chat Conductor Agent (Supervisor)
**Status**: Not yet implemented
**Purpose**: Route requests to specialist agents and aggregate responses

**Pattern**: Supervisor (LangGraph)

**Logic**:
1. Analyze user intent
2. Determine which specialist agent(s) to invoke
3. Invoke agents (can be parallel)
4. Aggregate responses
5. Synthesize final answer

---

## Memory System

### Vector Store

**File**: `backend/src/memory/vector_store.py`

Semantic memory using pgvector:

```python
# Store a learning
learning_id = await vector_store.store_learning(
    LearningCreate(
        content="Campaign X performs better on weekends",
        agent_name="performance_diagnosis",
        learning_type="pattern",
        confidence_score=0.9,
        source_session_id=session_id
    )
)

# Search for similar learnings
similar = await vector_store.search_similar(
    query="weekend performance",
    agent_name="performance_diagnosis",
    top_k=5,
    min_similarity=0.7
)

# Results include similarity scores
for learning in similar:
    print(f"{learning.content} (similarity: {learning.similarity:.2f})")
```

### Session Manager

**File**: `backend/src/memory/session_manager.py`

Conversation session management:

```python
# Create session
session_id = await session_manager.create_session(
    user_id="user123",
    metadata={"source": "web_ui"}
)

# Add messages
message_id = await session_manager.add_message(
    ChatMessageCreate(
        session_id=session_id,
        role="user",
        content="How is my campaign performing?"
    )
)

# Get session history
messages = await session_manager.get_messages(session_id)

# List user sessions
sessions = await session_manager.get_user_sessions(
    user_id="user123",
    limit=10
)
```

### Memory Types

1. **Short-term (Session Memory)**
   - Current conversation history
   - Stored in `messages` table
   - Lifetime: Duration of session

2. **Working Memory (Redis)**
   - Recent context across sessions
   - Stored in Redis
   - Lifetime: 1 hour (configurable)

3. **Long-term (Semantic Memory)**
   - Learnings and patterns
   - Stored in `agent_learnings` with embeddings
   - Lifetime: Permanent
   - Searchable via vector similarity

---

## Tools & Integrations

### Snowflake Tool

**File**: `backend/src/tools/snowflake_tool.py`

Query DV360 data from Snowflake:

```python
# Direct query
results = await snowflake_tool.execute_query(
    query="SELECT * FROM campaigns WHERE id = '123'",
    use_cache=True
)

# Helper methods
performance = await snowflake_tool.get_campaign_performance(
    campaign_id="123",
    start_date="2024-01-01",
    end_date="2024-01-31"
)

pacing = await snowflake_tool.get_budget_pacing(
    campaign_id="123",
    period_days=30
)

audience = await snowflake_tool.get_audience_performance(
    advertiser_id="456",
    min_impressions=1000
)

creative = await snowflake_tool.get_creative_performance(
    campaign_id="123"
)
```

**Features**:
- Async execution via thread pool
- Automatic query caching (Redis)
- Connection pooling
- Common DV360 query templates

### Decision Logger

**File**: `backend/src/tools/decision_logger.py`

Track all agent decisions:

```python
# Log a decision
decision_id = await decision_logger.log_decision(
    AgentDecisionCreate(
        session_id=session_id,
        message_id=message_id,
        agent_name="performance_diagnosis",
        decision_type="analysis",
        input_data={"campaign_id": "123"},
        output_data={"recommendation": "..."},
        tools_used=["snowflake_query"],
        reasoning="...",
        execution_time_ms=1500
    )
)

# Query decisions
decisions = await decision_logger.get_session_decisions(
    session_id=session_id,
    agent_name="performance_diagnosis"
)

# Analytics
stats = await decision_logger.get_agent_stats(
    agent_name="performance_diagnosis",
    days=7
)

tools = await decision_logger.get_most_used_tools(
    agent_name="performance_diagnosis"
)
```

### Memory Retrieval Tool

**Status**: Not yet implemented

Will combine:
- Vector similarity search
- Recent learnings
- Relevance ranking
- Context formatting

```python
# Future API
context = await memory_retrieval_tool.get_context(
    query="campaign performance",
    agent_name="performance_diagnosis",
    session_id=session_id
)
```

---

## API Specification

### Base URL

```
Development: http://localhost:8000
Production: https://api.dv360-agents.com
```

### Authentication

**Status**: Not yet implemented

Future: JWT-based authentication

```
Authorization: Bearer <token>
```

### Health Endpoints

#### GET /health

Overall system health:

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "checks": {
    "database": true,
    "redis": true
  }
}
```

#### GET /health/liveness

Kubernetes liveness probe:

```json
{
  "status": "alive"
}
```

#### GET /health/readiness

Kubernetes readiness probe:

```json
{
  "status": "ready",
  "database": true,
  "redis": true
}
```

### Chat Endpoints

**Status**: Not yet implemented

#### POST /api/chat

Send a message and get agent response:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How is campaign X performing?",
    "session_id": "optional-uuid",
    "user_id": "user123",
    "stream": false
  }'
```

Response:
```json
{
  "session_id": "uuid",
  "message_id": "uuid",
  "response": "Campaign X is performing well...",
  "agent_name": "performance_diagnosis",
  "reasoning": "I analyzed the metrics...",
  "tools_used": ["snowflake_query"],
  "execution_time_ms": 2500,
  "metadata": {}
}
```

#### WebSocket /ws/chat

**Status**: Not yet implemented

Streaming chat responses:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/chat?session_id=uuid');

ws.onmessage = (event) => {
  const chunk = JSON.parse(event.data);
  // chunk.type: 'token', 'agent', 'tool', 'complete', 'error'
  // chunk.content: text content
};

ws.send(JSON.stringify({
  message: "How is campaign X performing?",
  user_id: "user123"
}));
```

### Session Endpoints

**Status**: Not yet implemented

#### POST /api/sessions

Create a new session:

```bash
curl -X POST http://localhost:8000/api/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "metadata": {"source": "web"}
  }'
```

Response:
```json
{
  "id": "uuid",
  "user_id": "user123",
  "created_at": "2024-01-12T10:00:00Z",
  "updated_at": "2024-01-12T10:00:00Z",
  "message_count": 0,
  "metadata": {"source": "web"}
}
```

#### GET /api/sessions

List user sessions:

```bash
curl http://localhost:8000/api/sessions?user_id=user123&limit=10
```

Response:
```json
{
  "sessions": [
    {
      "id": "uuid",
      "user_id": "user123",
      "created_at": "2024-01-12T10:00:00Z",
      "updated_at": "2024-01-12T10:05:00Z",
      "message_count": 5,
      "metadata": {}
    }
  ],
  "total": 1
}
```

#### GET /api/sessions/{session_id}

Get session with full message history:

```bash
curl http://localhost:8000/api/sessions/{uuid}
```

Response:
```json
{
  "session": {
    "id": "uuid",
    "user_id": "user123",
    "created_at": "2024-01-12T10:00:00Z",
    "updated_at": "2024-01-12T10:05:00Z",
    "message_count": 4,
    "metadata": {}
  },
  "messages": [
    {
      "id": "uuid",
      "session_id": "uuid",
      "role": "user",
      "content": "How is campaign X performing?",
      "agent_name": null,
      "timestamp": "2024-01-12T10:00:00Z",
      "metadata": {}
    },
    {
      "id": "uuid",
      "session_id": "uuid",
      "role": "assistant",
      "content": "Campaign X is performing well...",
      "agent_name": "performance_diagnosis",
      "timestamp": "2024-01-12T10:00:05Z",
      "metadata": {}
    }
  ]
}
```

#### DELETE /api/sessions/{session_id}

Delete a session:

```bash
curl -X DELETE http://localhost:8000/api/sessions/{uuid}
```

Response:
```json
{
  "success": true,
  "message": "Session deleted"
}
```

### Metrics Endpoint

#### GET /metrics

Prometheus metrics (already implemented):

```bash
curl http://localhost:8000/metrics
```

Returns Prometheus text format with metrics:
- HTTP request metrics
- Agent execution metrics
- LLM token usage
- Database query metrics
- Cache operations

---

## Deployment

### Local Development

```bash
# Setup
cp .env.example .env
# Edit .env with your credentials

# Start services
cd infrastructure
docker-compose up -d

# Run migrations
docker exec -it dv360-backend alembic upgrade head

# View logs
docker-compose logs -f backend
```

### Production-like Testing

```bash
# Start with multiple backend replicas
cd infrastructure
docker-compose -f docker-compose.prod.yml up -d --scale backend=5

# Services:
# - Backend (5 replicas): Load balanced via Nginx
# - Nginx: http://localhost:8000
# - Prometheus: http://localhost:9090
# - Grafana: http://localhost:3001
```

### Kubernetes Deployment

**Status**: Configuration ready, not yet deployed

```bash
# Apply manifests
kubectl apply -f infrastructure/k8s/

# Services deployed:
# - Backend deployment (auto-scaling)
# - PostgreSQL statefulset
# - Redis deployment
# - Nginx ingress
```

### Environment Variables

Required environment variables (see `.env.example`):

```bash
# LLM Configuration (RECOMMENDED: Use both)
# Anthropic Claude for agent reasoning (prioritized)
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-opus-20240229

# OpenAI for embeddings only (required for semantic memory)
OPENAI_API_KEY=sk-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# PostgreSQL (Custom configuration)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=dv360agent
POSTGRES_USER=dvdbowner
POSTGRES_PASSWORD=dvagentlangchain

# Redis Cloud (Production)
REDIS_HOST=redis-10054.c338.eu-west-2-1.ec2.cloud.redislabs.com
REDIS_PORT=10054
REDIS_PASSWORD=your_password_here
REDIS_URL=redis://default:password@redis-10054...

# Snowflake (Production)
SNOWFLAKE_ACCOUNT=ai60319.eu-west-1
SNOWFLAKE_USER=neilblyth@sub2tech.com
SNOWFLAKE_PASSWORD=***
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_DATABASE=REPORTS
SNOWFLAKE_SCHEMA=METRICS
SNOWFLAKE_ROLE=SYSADMIN

# LangSmith (Optional debugging)
LANGCHAIN_API_KEY=lsv2_pt_...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=dv360-agent-system
```

### Production Configuration

**Current Deployment:**

**LLM Provider:**
- **Primary**: Anthropic Claude 3 Opus (agent reasoning)
- **Secondary**: OpenAI text-embedding-3-small (embeddings only)
- **Cost**: ~$15-75 per 1M tokens (Claude) + $0.02 per 1M tokens (embeddings)

**Database:**
- **Type**: PostgreSQL 16 with pgvector
- **Database**: dv360agent
- **User**: dvdbowner
- **Deployment**: Docker container (local), can migrate to RDS/Cloud SQL

**Cache:**
- **Provider**: Redis Cloud (free tier)
- **Endpoint**: redis-10054.c338.eu-west-2-1.ec2.cloud.redislabs.com:10054
- **Region**: EU West 2 (London)
- **Limits**: 30MB storage, 30 connections

**Data Source:**
- **Platform**: Snowflake
- **Account**: ai60319.eu-west-1
- **Database**: REPORTS
- **Schema**: METRICS
- **Warehouse**: COMPUTE_WH

**Monitoring:**
- **LangSmith**: Enabled for agent debugging and tracing
- **Prometheus**: Metrics collection enabled
- **Grafana**: Available on port 3001

### Scaling Configuration

**Horizontal Scaling:**
- Backend is stateless
- Can scale to N replicas
- Load balanced via Nginx
- Session state in Redis (shared)

**Database Scaling:**
- PostgreSQL connection pooling (20 connections per replica)
- Read replicas (future)
- Connection limits prevent overload

**Redis Scaling:**
- Redis Cloud (managed service) - currently free tier
- 30MB storage, 30 concurrent connections
- Upgrade to paid plans for increased capacity
- Multi-zone high availability included
- Automatic key eviction (LRU) configured

---

## Implementation Status

### Sprint 1: Foundation ✅ (100% Complete)

- [x] Project structure
- [x] Configuration management
- [x] Database setup (PostgreSQL + pgvector)
- [x] Redis caching
- [x] FastAPI application
- [x] Health endpoints
- [x] Docker Compose (dev + prod)
- [x] Database migrations
- [x] Logging & metrics
- [x] Documentation

**Delivered**: 12 files, production-ready infrastructure

### Sprint 2: Core Agents ⏳ (50% Complete)

**Completed:**
- [x] Pydantic schemas (agent, chat, memory)
- [x] Base agent class with LangGraph
- [x] Decision logger tool
- [x] Snowflake tool
- [x] Vector store (semantic memory)
- [x] Session manager

**Remaining:**
- [ ] Memory retrieval tool
- [ ] Performance Diagnosis Agent
- [ ] Chat Conductor Agent
- [ ] Chat API endpoints
- [ ] Session API endpoints
- [ ] End-to-end testing

**Delivered**: 8 files, ~1,500 lines of code

### Sprint 3: Remaining Agents (Not Started)

- [ ] Budget & Pacing Agent
- [ ] Audience & Targeting Agent
- [ ] Creative & Inventory Agent
- [ ] Seasonality context tool
- [ ] WebSocket streaming
- [ ] Parallel agent execution

### Sprint 4: Memory & Intelligence (Not Started)

- [ ] Learning extraction logic
- [ ] Automatic insight generation
- [ ] Pattern recognition
- [ ] User preference learning

### Sprint 5: Scale & Production (Not Started)

- [ ] Load testing & optimization
- [ ] Rate limiting enforcement
- [ ] Authentication & authorization
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Performance benchmarks

### Sprint 6: Testing & Docs (Not Started)

- [ ] Unit tests
- [ ] Integration tests
- [ ] Load tests
- [ ] API documentation
- [ ] Deployment guides

---

## Future Roadmap

### Phase 1: Complete Core Agents (Sprint 2-3)
**Timeline**: 2-3 weeks

- Complete Performance Diagnosis Agent
- Implement Chat Conductor
- Add remaining specialist agents
- Full API implementation

### Phase 2: Enhanced Intelligence (Sprint 4)
**Timeline**: 2-3 weeks

- Automatic learning extraction
- Pattern recognition
- Insight generation
- Multi-agent collaboration

### Phase 3: Production Readiness (Sprint 5-6)
**Timeline**: 2-3 weeks

- Comprehensive testing
- Load testing & optimization
- Security hardening
- Documentation

### Phase 4: Advanced Features
**Timeline**: Future

- **Write Operations**: Allow agents to make changes to DV360
- **Proactive Monitoring**: Agents monitor campaigns and alert
- **Scheduled Analysis**: Daily/weekly reports
- **Custom Agents**: User-defined specialist agents
- **Multi-tenancy**: Support multiple organizations
- **Advanced Analytics**: Predictive modeling, forecasting
- **Integration Hub**: Connect to more data sources

---

## Performance Targets

### Response Time
- **Chat Response**: < 3 seconds (p95)
- **Streaming First Token**: < 500ms
- **Database Queries**: < 100ms (p95)
- **Vector Search**: < 200ms (p95)

### Throughput
- **Concurrent Sessions**: 100+
- **Requests per Second**: 50+
- **Messages per Day**: 100,000+

### Availability
- **Uptime**: 99.9% (production target)
- **Error Rate**: < 0.1%

---

## Security Considerations

### Current Status
- [x] HTTPS/TLS support (via Nginx)
- [x] CORS configuration
- [x] Environment-based secrets
- [ ] Authentication (not yet implemented)
- [ ] Authorization (not yet implemented)
- [ ] Rate limiting (implemented, not enforced)

### Future Security
- JWT authentication
- Role-based access control (RBAC)
- API key management
- Audit logging
- Secrets management (Vault)
- Input sanitization
- SQL injection prevention (using parameterized queries)

---

## Monitoring & Observability

### Metrics Collected

**HTTP Metrics:**
- Request count (by method, endpoint, status)
- Request duration (histogram)

**Agent Metrics:**
- Execution count (by agent, status)
- Execution duration (histogram)
- Tool call count (by agent, tool)

**LLM Metrics:**
- Request count (by provider, model)
- Token usage (input/output)
- Request duration

**Database Metrics:**
- Query count (by operation, table)
- Query duration (histogram)

**Cache Metrics:**
- Operation count (by operation, status)
- Hit/miss rates

**Memory Metrics:**
- Retrieval count (by agent)
- Storage count (by agent, type)

### Dashboards

**Grafana Dashboards** (configured but not yet deployed):
1. API Overview: Request rates, latency, errors
2. Agent Performance: Execution times, success rates
3. LLM Usage: Token consumption, costs
4. Database Performance: Query times, connection pool
5. System Resources: CPU, memory, disk

---

## Code Quality Standards

### Python Style
- **Formatter**: Black (120 char line length)
- **Linter**: Ruff
- **Type Checking**: mypy (configured, not enforced)
- **Docstrings**: Google style

### Testing
- **Framework**: pytest
- **Coverage Target**: 80%+
- **Types**: Unit, integration, load

### Git Workflow
- Feature branches
- Pull request reviews
- Commit message format: conventional commits

---

## Support & Maintenance

### Development Team
- Backend: Python/FastAPI
- Agents: LangChain/LangGraph
- Infrastructure: Docker/K8s
- Data: Snowflake/PostgreSQL

### Documentation
- **README.md**: Quick start guide
- **spec.md**: This document (technical specification)
- **docs/**: Sprint summaries, architecture docs
- **Code**: Inline docstrings

### Contact
- GitHub Issues: [Repository URL]
- Documentation: `/docs`
- API Docs: http://localhost:8000/docs (when running)

---

## Appendix

### File Structure

```
dv360-agent-system/
├── backend/
│   ├── src/
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── base.py ✅
│   │   │   ├── conductor.py ⏳
│   │   │   ├── performance_agent.py ⏳
│   │   │   ├── budget_agent.py
│   │   │   ├── audience_agent.py
│   │   │   └── creative_agent.py
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── snowflake_tool.py ✅
│   │   │   ├── seasonality_tool.py
│   │   │   ├── memory_tool.py ⏳
│   │   │   └── decision_logger.py ✅
│   │   ├── memory/
│   │   │   ├── __init__.py
│   │   │   ├── vector_store.py ✅
│   │   │   ├── session_manager.py ✅
│   │   │   └── learning_store.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── main.py ✅
│   │   │   ├── routes/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── chat.py ⏳
│   │   │   │   ├── sessions.py ⏳
│   │   │   │   └── health.py ✅
│   │   │   └── websocket.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py ✅
│   │   │   ├── database.py ✅
│   │   │   ├── cache.py ✅
│   │   │   └── telemetry.py ✅
│   │   └── schemas/
│   │       ├── __init__.py
│   │       ├── agent.py ✅
│   │       ├── chat.py ✅
│   │       └── memory.py ✅
│   ├── tests/
│   ├── alembic/ ✅
│   ├── Dockerfile ✅
│   ├── requirements.txt ✅
│   └── pyproject.toml ✅
├── infrastructure/
│   ├── docker-compose.yml ✅
│   ├── docker-compose.prod.yml ✅
│   ├── nginx.conf ✅
│   ├── prometheus.yml ✅
│   ├── init-db.sql ✅
│   └── k8s/
├── docs/
│   ├── LANGSMITH_TRACING_GUIDE.md ✅
│   ├── TESTING_GUIDE.md ✅
│   ├── SNOWFLAKE_QUERY_GUIDE.md ✅
│   └── PRODUCTION_CONFIG.md ✅
├── .env.example ✅
├── .gitignore ✅
├── Makefile ✅
├── quick-start.sh ✅
├── README.md ✅
└── spec.md ✅ (this file)

Legend:
✅ Complete
⏳ In progress
(blank) Not started
```

### Dependencies

See `backend/requirements.txt` for full list. Key dependencies:

- fastapi==0.109.2
- langchain==0.1.6
- langgraph==0.0.20
- asyncpg==0.29.0
- redis==5.0.1
- snowflake-connector-python==3.6.0
- structlog==24.1.0
- prometheus-client==0.19.0
- pytest==8.0.0

### Version History

- **v0.1.0** (2024-01-12): Sprint 1 complete, Sprint 2 50% complete
  - Foundation infrastructure
  - Core framework started
  - Memory system operational

---

**End of Specification Document**

For the latest updates, see:
- `SYSTEM_STATUS.md` - Current system status
- `RECENT_CHANGES.md` - Latest updates and changes
- `COMPLETE_SYSTEM_SUMMARY.md` - Complete system overview
- `README.md` - Quick start guide
- GitHub repository - Source code
