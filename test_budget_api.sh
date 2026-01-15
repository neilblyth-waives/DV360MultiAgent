#!/bin/bash
# Test script for budget risk agent via API

echo "Testing Budget Risk Agent"
echo "Query: 'what is the current budget for Quiz for Jan'"
echo ""

curl -X POST http://localhost:8000/api/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "what is the current budget for Quiz for Jan",
    "user_id": "test_user"
  }' | python3 -m json.tool

echo ""
echo "Done!"

