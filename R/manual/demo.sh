#!/bin/sh

set -eu

base_url="${KST_BASE_URL:-http://127.0.0.1:8000}"
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if ! command -v curl >/dev/null 2>&1; then
  echo "This demo requires curl." >&2
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "This demo requires jq." >&2
  exit 1
fi

echo "1. Health check"
health_response=$(
  curl --fail-with-body --silent --show-error \
    "$base_url/health"
)
printf '%s\n' "$health_response" | jq .

echo
echo "2. Create the KST model"
model_response=$(
  curl --fail-with-body --silent --show-error \
    --request POST \
    --header "Content-Type: application/json" \
    --data-binary "@$script_dir/model-request.json" \
    "$base_url/internal/v1/kst/model"
)
printf '%s\n' "$model_response" | jq .

model=$(printf '%s\n' "$model_response" | jq '.model')
posterior=$(printf '%s\n' "$model_response" | jq '.posterior')
next_node=$(printf '%s\n' "$model_response" | jq -r '.next_node')
response_count=1

echo
echo "3. Answer each selected node correctly until the assessment completes"
while [ "$response_count" -le 50 ]; do
  echo
  echo "Answer $response_count: node=$next_node, correct=true"
  advance_request=$(
    jq -n \
      --argjson model "$model" \
      --argjson posterior "$posterior" \
      --arg question_node "$next_node" \
      --argjson response_count "$response_count" \
      '{
        model: $model,
        posterior: $posterior,
        question_node: $question_node,
        response_correct: true,
        response_count: $response_count
      }'
  )
  advance_response=$(
    printf '%s\n' "$advance_request" |
      curl --fail-with-body --silent --show-error \
        --request POST \
        --header "Content-Type: application/json" \
        --data-binary @- \
        "$base_url/internal/v1/kst/advance"
  )
  printf '%s\n' "$advance_response" | jq .

  status=$(printf '%s\n' "$advance_response" | jq -r '.status')
  if [ "$status" = "completed" ]; then
    echo
    echo "Assessment completed."
    exit 0
  fi

  posterior=$(printf '%s\n' "$advance_response" | jq '.posterior')
  next_node=$(printf '%s\n' "$advance_response" | jq -r '.next_node')
  response_count=$((response_count + 1))
done

echo "The assessment did not complete within 50 responses." >&2
exit 1
