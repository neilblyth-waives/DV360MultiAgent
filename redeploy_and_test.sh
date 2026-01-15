#!/bin/bash
# Redeploy backend and test budget agent

echo "🔨 Rebuilding backend..."
docker-compose build --no-cache backend

echo ""
echo "🚀 Starting backend..."
docker-compose up -d backend

echo ""
echo "⏳ Waiting for backend to be ready..."
sleep 10

echo ""
echo "✅ Checking health..."
curl -s http://localhost:8000/health/liveness | python3 -m json.tool

echo ""
echo "🧪 Testing Budget Risk Agent..."
echo "Query: 'what is the current budget for Quiz for Jan'"
echo ""

curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "what is the current budget for Quiz for Jan",
    "user_id": "test_user"
  }' | python3 -m json.tool

echo ""
echo "✅ Done!"

