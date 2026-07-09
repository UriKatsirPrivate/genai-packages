#!/usr/bin/env bash
# Quick demo against a locally running server (uvicorn app.main:app).
set -euo pipefail

BASE="${1:-http://localhost:8000}"

echo "== healthz =="
curl -sf "$BASE/healthz" | jq .

echo
echo "== optimize: earnings-report extraction (with an existing naive prompt) =="
curl -sf "$BASE/optimize" -H 'content-type: application/json' -d '{
  "use_case": "Answer questions about figures in quarterly earnings reports, including growth calculations. Users paste the report text. Wrong numbers are costly; if a figure is not in the report the assistant must say so.",
  "existing_prompt": "What was the revenue and how much did it grow over last quarter?"
}' | jq '{optimized_prompt, revised, applied: [.techniques[] | select(.relevant) | {id: .technique_id, priority, application}], skipped: [.techniques[] | select(.relevant | not) | .technique_id], approved: .critic.approved}'
