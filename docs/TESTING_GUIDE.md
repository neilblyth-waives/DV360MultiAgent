# System Testing Guide

**Purpose:** Verify all components are working correctly before continuing with agent implementation.

---

## Testing Checklist

### Phase 1: Start Services ✅

```bash
# Navigate to infrastructure folder
cd /Users/neilblyth/Documents/Apps/TestAgentMemory/infrastructure

# Start services (PostgreSQL + Backend)
docker-compose up -d

# Check services are running
docker ps

# You should see:
# - dv360-postgres (running)
# - dv360-backend (running)
```

**Expected Output:**
```
✔ Container dv360-postgres  Started
✔ Container dv360-backend   Started
```

---

## Phase 2: Verify Services

### Test 1: Check Backend Logs

```bash
docker logs dv360-backend
```

**Look for these lines:**
```
✓ Database initialized: postgres:5432/dv360agent
✓ Redis initialized: redis-10054.c338.eu-west-2-1.ec2.cloud.redislabs.com:10054
INFO: Using Anthropic Claude for LLM model=claude-3-opus-20240229
INFO: Using OpenAI for embeddings model=text-embedding-3-small
✓ pgvector extension ensured
Application startup complete
```

**If you see errors:**
- Check `.env` file exists in project root
- Verify all credentials are correct
- Check Redis Cloud password is correct

### Test 2: Check PostgreSQL

```bash
# Check PostgreSQL logs
docker logs dv360-postgres | tail -20

# Should see:
# database system is ready to accept connections
```

**Connect to database:**
```bash
docker exec -it dv360-postgres psql -U dvdbowner -d dv360agent

# In psql, run:
\dt                          # List tables (should be empty before migration)
SELECT extname FROM pg_extension;  # Should see 'vector' and 'uuid-ossp'
\q                           # Exit
```

### Test 3: Health Check Endpoint

```bash
curl http://localhost:8000/health
```

**Expected Response:**
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

**If database or redis is false:**
- Check backend logs for errors
- Verify credentials in `.env`
- Check Redis Cloud is accessible

### Test 4: API Documentation

Open in browser:
```
http://localhost:8000/docs
```

**You should see:**
- FastAPI Swagger UI
- `/health` endpoints listed
- OpenAPI documentation

---

## Phase 3: Run Database Migrations

```bash
# Run migrations
docker exec -it dv360-backend alembic upgrade head

# Expected output:
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> 001, initial schema
```

**Verify tables were created:**
```bash
docker exec -it dv360-postgres psql -U dvdbowner -d dv360agent -c "\dt"

# Should see:
# - sessions
# - messages
# - agent_decisions
# - agent_learnings
# - query_cache
```

**Check vector index:**
```bash
docker exec -it dv360-postgres psql -U dvdbowner -d dv360agent -c "\d agent_learnings"

# Should see 'embedding' column with type 'vector(1536)'
```

---

## Phase 4: Component Testing

### Test 5: Test Redis Connection

```bash
# Test from backend container
docker exec -it dv360-backend python << 'EOF'
import asyncio
from src.core.cache import check_redis_health

async def test():
    result = await check_redis_health()
    print(f"Redis Health: {result}")

asyncio.run(test())
EOF
```

**Expected Output:**
```
Redis Health: True
```

### Test 6: Test Database Connection

```bash
docker exec -it dv360-backend python << 'EOF'
import asyncio
from src.core.database import check_db_health

async def test():
    result = await check_db_health()
    print(f"Database Health: {result}")

asyncio.run(test())
EOF
```

**Expected Output:**
```
Database Health: True
```

### Test 7: Test Session Manager

```bash
docker exec -it dv360-backend python << 'EOF'
import asyncio
from src.memory.session_manager import session_manager

async def test():
    # Create a session
    session_id = await session_manager.create_session(
        user_id="test_user",
        metadata={"source": "test"}
    )
    print(f"✓ Created session: {session_id}")

    # Get session info
    info = await session_manager.get_session_info(session_id)
    print(f"✓ Retrieved session: {info.user_id}")

    # Add a message
    from src.schemas.chat import ChatMessageCreate
    msg_id = await session_manager.add_message(
        ChatMessageCreate(
            session_id=session_id,
            role="user",
            content="Test message"
        )
    )
    print(f"✓ Added message: {msg_id}")

    # Get messages
    messages = await session_manager.get_messages(session_id)
    print(f"✓ Retrieved {len(messages)} messages")
    print("✅ Session manager working!")

asyncio.run(test())
EOF
```

**Expected Output:**
```
✓ Created session: [UUID]
✓ Retrieved session: test_user
✓ Added message: [UUID]
✓ Retrieved 1 messages
✅ Session manager working!
```

### Test 8: Test Decision Logger

```bash
docker exec -it dv360-backend python << 'EOF'
import asyncio
from uuid import uuid4
from src.tools.decision_logger import decision_logger
from src.schemas.agent import AgentDecisionCreate

async def test():
    session_id = uuid4()

    # Log a decision
    decision_id = await decision_logger.log_decision(
        AgentDecisionCreate(
            session_id=session_id,
            agent_name="test_agent",
            decision_type="test",
            input_data={"test": "input"},
            output_data={"test": "output"},
            tools_used=["test_tool"],
            reasoning="Test reasoning",
            execution_time_ms=100
        )
    )
    print(f"✓ Logged decision: {decision_id}")

    # Get decisions
    decisions = await decision_logger.get_session_decisions(session_id)
    print(f"✓ Retrieved {len(decisions)} decisions")
    print("✅ Decision logger working!")

asyncio.run(test())
EOF
```

**Expected Output:**
```
✓ Logged decision: [UUID]
✓ Retrieved 1 decisions
✅ Decision logger working!
```

### Test 9: Test Vector Store (Embeddings)

```bash
docker exec -it dv360-backend python << 'EOF'
import asyncio
from uuid import uuid4
from src.memory.vector_store import vector_store
from src.schemas.memory import LearningCreate

async def test():
    # Store a learning
    learning_id = await vector_store.store_learning(
        LearningCreate(
            content="Campaign performance improves on weekends",
            agent_name="test_agent",
            learning_type="pattern",
            confidence_score=0.9,
            source_session_id=uuid4()
        )
    )
    print(f"✓ Stored learning with embedding: {learning_id}")

    # Search for similar
    results = await vector_store.search_similar(
        query="weekend performance",
        agent_name="test_agent",
        top_k=5,
        min_similarity=0.5
    )
    print(f"✓ Found {len(results)} similar learnings")
    if results:
        print(f"  Best match: '{results[0].content}' (similarity: {results[0].similarity:.3f})")
    print("✅ Vector store working!")

asyncio.run(test())
EOF
```

**Expected Output:**
```
✓ Stored learning with embedding: [UUID]
✓ Found 1 similar learnings
  Best match: 'Campaign performance improves on weekends' (similarity: 0.XXX)
✅ Vector store working!
```

**If embeddings fail:**
- Check OPENAI_API_KEY is valid
- Check internet connectivity
- Verify OpenAI billing is set up

### Test 10: Test Snowflake Connection

```bash
docker exec -it dv360-backend python << 'EOF'
import asyncio
from src.tools.snowflake_tool import snowflake_tool

async def test():
    try:
        # Test simple query
        result = await snowflake_tool.execute_query(
            query="SELECT CURRENT_VERSION() as version",
            use_cache=False
        )
        print(f"✓ Snowflake connection successful")
        print(f"  Version: {result[0]['VERSION']}")
        print("✅ Snowflake working!")
    except Exception as e:
        print(f"❌ Snowflake error: {e}")
        print("Check credentials in .env file")

asyncio.run(test())
EOF
```

**Expected Output:**
```
✓ Snowflake connection successful
  Version: 8.X.X
✅ Snowflake working!
```

**If Snowflake fails:**
- Check SNOWFLAKE_* credentials in `.env`
- Verify warehouse is running
- Check network access to Snowflake

---

## Phase 5: Integration Tests

### Test 11: End-to-End Flow

```bash
docker exec -it dv360-backend python << 'EOF'
import asyncio
from uuid import uuid4
from src.memory.session_manager import session_manager
from src.schemas.chat import ChatMessageCreate
from src.tools.decision_logger import decision_logger
from src.schemas.agent import AgentDecisionCreate
from src.memory.vector_store import vector_store
from src.schemas.memory import LearningCreate

async def test():
    print("🧪 Running end-to-end integration test...\n")

    # 1. Create session
    session_id = await session_manager.create_session(
        user_id="integration_test",
        metadata={"test": "e2e"}
    )
    print(f"✓ Step 1: Created session {session_id}")

    # 2. Add user message
    user_msg_id = await session_manager.add_message(
        ChatMessageCreate(
            session_id=session_id,
            role="user",
            content="How is my campaign performing?"
        )
    )
    print(f"✓ Step 2: Added user message")

    # 3. Log agent decision
    decision_id = await decision_logger.log_decision(
        AgentDecisionCreate(
            session_id=session_id,
            message_id=user_msg_id,
            agent_name="performance_diagnosis",
            decision_type="analysis",
            input_data={"campaign_id": "test123"},
            output_data={"status": "analyzed"},
            tools_used=["snowflake_query", "memory_retrieval"],
            reasoning="Analyzed campaign performance metrics",
            execution_time_ms=1500
        )
    )
    print(f"✓ Step 3: Logged agent decision")

    # 4. Store learning
    learning_id = await vector_store.store_learning(
        LearningCreate(
            content="Test campaign shows strong performance on mobile devices",
            agent_name="performance_diagnosis",
            learning_type="insight",
            confidence_score=0.85,
            source_session_id=session_id
        )
    )
    print(f"✓ Step 4: Stored learning with embedding")

    # 5. Add assistant response
    assistant_msg_id = await session_manager.add_message(
        ChatMessageCreate(
            session_id=session_id,
            role="assistant",
            content="Your campaign is performing well, especially on mobile.",
            agent_name="performance_diagnosis"
        )
    )
    print(f"✓ Step 5: Added assistant message")

    # 6. Verify session history
    messages = await session_manager.get_messages(session_id)
    print(f"✓ Step 6: Retrieved {len(messages)} messages from session")

    # 7. Search for similar learnings
    similar = await vector_store.search_similar(
        query="mobile performance",
        agent_name="performance_diagnosis",
        top_k=3
    )
    print(f"✓ Step 7: Found {len(similar)} similar learnings")

    # 8. Get agent stats
    stats = await decision_logger.get_agent_stats("performance_diagnosis", days=1)
    print(f"✓ Step 8: Agent stats - {stats.get('total_decisions', 0)} total decisions")

    print("\n✅ End-to-end integration test PASSED!")
    print("All components working together correctly.")

asyncio.run(test())
EOF
```

**Expected Output:**
```
🧪 Running end-to-end integration test...

✓ Step 1: Created session [UUID]
✓ Step 2: Added user message
✓ Step 3: Logged agent decision
✓ Step 4: Stored learning with embedding
✓ Step 5: Added assistant message
✓ Step 6: Retrieved 2 messages from session
✓ Step 7: Found 1 similar learnings
✓ Step 8: Agent stats - 1 total decisions

✅ End-to-end integration test PASSED!
All components working together correctly.
```

---

## Phase 6: Monitoring

### Test 12: Prometheus Metrics

```bash
curl http://localhost:8000/metrics | head -50
```

**Should see metrics like:**
```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{endpoint="/health",method="GET",status="200"} 5.0

# HELP db_queries_total Total database queries
# TYPE db_queries_total counter
db_queries_total{operation="insert",table="sessions"} 1.0
```

### Test 13: LangSmith Tracing

Check LangSmith console:
1. Go to https://smith.langchain.com/
2. Sign in
3. Find project: `dv360-agent-system`
4. Should see traces when LLM/embeddings are called

---

## Test Results Summary

Create a test report:

```bash
cat > /tmp/test_results.md << 'EOF'
# System Test Results

**Date:** $(date)
**Tester:** [Your Name]

## Results

| Test | Component | Status | Notes |
|------|-----------|--------|-------|
| 1 | Backend Startup | ⬜ Pass / ❌ Fail | |
| 2 | PostgreSQL | ⬜ Pass / ❌ Fail | |
| 3 | Health Endpoint | ⬜ Pass / ❌ Fail | |
| 4 | API Docs | ⬜ Pass / ❌ Fail | |
| 5 | Database Migrations | ⬜ Pass / ❌ Fail | |
| 6 | Redis Connection | ⬜ Pass / ❌ Fail | |
| 7 | Session Manager | ⬜ Pass / ❌ Fail | |
| 8 | Decision Logger | ⬜ Pass / ❌ Fail | |
| 9 | Vector Store | ⬜ Pass / ❌ Fail | |
| 10 | Snowflake | ⬜ Pass / ❌ Fail | |
| 11 | End-to-End | ⬜ Pass / ❌ Fail | |

## Issues Found

[List any issues here]

## Next Steps

[What needs to be fixed or implemented next]
EOF
```

---

## Common Issues & Solutions

### Issue: Backend won't start

**Symptoms:** Container exits immediately

**Check:**
```bash
docker logs dv360-backend
```

**Solutions:**
- Verify `.env` file exists in project root
- Check all required environment variables are set
- Verify Python syntax in source files

### Issue: Database connection failed

**Symptoms:** `database: false` in health check

**Solutions:**
- Check PostgreSQL container is running: `docker ps`
- Verify DATABASE_URL in `.env` matches docker-compose settings
- Check PostgreSQL logs: `docker logs dv360-postgres`

### Issue: Redis connection failed

**Symptoms:** `redis: false` in health check

**Solutions:**
- Verify Redis Cloud password is correct
- Check Redis Cloud database is running (https://app.redislabs.com/)
- Test connection manually with redis-cli
- Ensure password is URL-encoded in REDIS_URL

### Issue: Embeddings not working

**Symptoms:** Vector store test fails

**Solutions:**
- Check OPENAI_API_KEY is valid
- Verify OpenAI billing is set up
- Check internet connectivity
- Try with a different embedding model

### Issue: Snowflake connection failed

**Symptoms:** Snowflake test fails with auth error

**Solutions:**
- Verify all SNOWFLAKE_* variables in `.env`
- Check account format: `account.region`
- Ensure warehouse is running in Snowflake console
- Verify user has correct permissions

---

## Performance Benchmarks

After all tests pass, run benchmarks:

```bash
# Measure health check latency
time curl http://localhost:8000/health

# Should be < 100ms

# Measure database query time
docker exec -it dv360-backend python << 'EOF'
import asyncio
import time
from src.memory.session_manager import session_manager

async def test():
    start = time.time()
    session_id = await session_manager.create_session("perf_test")
    duration = time.time() - start
    print(f"Session creation: {duration*1000:.2f}ms")

asyncio.run(test())
EOF
```

**Expected Performance:**
- Health check: < 100ms
- Session creation: < 50ms
- Database query: < 100ms
- Redis operation: < 10ms
- Vector search: < 200ms

---

## Ready for Development

Once all tests pass:

✅ Infrastructure working
✅ Database operational
✅ Cache operational
✅ All tools functional
✅ Memory system working

**Next:** Continue with Sprint 2 implementation
- Memory retrieval tool
- Performance Diagnosis Agent
- Chat Conductor Agent
- Chat API endpoints

---

**Status:** Ready for testing
**Run:** Follow the phases above sequentially
