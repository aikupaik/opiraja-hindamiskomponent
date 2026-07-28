#!/bin/sh

set -eu

base_url="${KST_BASE_URL:-http://127.0.0.1:8001}"
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if ! command -v curl >/dev/null 2>&1; then
  echo "This demo requires curl." >&2
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "This demo requires jq." >&2
  exit 1
fi

post_json() {
  endpoint=$1
  curl --fail-with-body --silent --show-error \
    --request POST \
    --header "Content-Type: application/json" \
    --data-binary @- \
    "$base_url$endpoint"
}

echo "1. Health check"
health_response=$(
  curl --fail-with-body --silent --show-error \
    "$base_url/health"
)
printf '%s\n' "$health_response" | jq .

echo
echo "2. Create the v2 KST model"
model_response=$(
  post_json "/internal/v2/kst/model" < "$script_dir/model-v2-request.json"
)
printf '%s\n' "$model_response" | jq .

model=$(printf '%s\n' "$model_response" | jq -e '.model')
posterior=$(printf '%s\n' "$model_response" | jq -e '.posterior')
candidates=$(jq -e '.' "$script_dir/candidates-v2.json")

echo
echo "3. Select the first candidate from the experiment inventory"
select_request=$(
  jq -n \
    --argjson model "$model" \
    --argjson posterior "$posterior" \
    --argjson candidates "$candidates" \
    '{
      model: $model,
      posterior: $posterior,
      candidates: $candidates
    }'
)
selected_response=$(
  printf '%s\n' "$select_request" |
    post_json "/internal/v2/kst/select"
)
printf '%s\n' "$selected_response" | jq .

candidate_id=$(printf '%s\n' "$selected_response" | jq -er '.candidate_id')
candidate_node=$(printf '%s\n' "$selected_response" | jq -er '.node')
response_count=1

echo
echo "4. Answer each selected candidate correctly, without reuse"
while :; do
  administered=$(
    printf '%s\n' "$candidates" |
      jq -e \
        --arg candidate_id "$candidate_id" \
        --arg node "$candidate_node" \
        '
          map(select(
            .candidate_id == $candidate_id and .node == $node
          )) |
          if length == 1 then
            .[0]
          else
            error("selected candidate is not uniquely present in the inventory")
          end
        '
  )
  remaining_candidates=$(
    printf '%s\n' "$candidates" |
      jq \
        --arg candidate_id "$candidate_id" \
        '[.[] | select(.candidate_id != $candidate_id)]'
  )

  echo
  echo "Answer $response_count: candidate=$candidate_id, node=$candidate_node, correct=true"
  advance_request=$(
    jq -n \
      --argjson model "$model" \
      --argjson posterior "$posterior" \
      --argjson administered "$administered" \
      --argjson response_count "$response_count" \
      --argjson remaining_candidates "$remaining_candidates" \
      '{
        model: $model,
        posterior: $posterior,
        administered: $administered,
        response_correct: true,
        response_count: $response_count,
        remaining_candidates: $remaining_candidates
      }'
  )
  advance_response=$(
    printf '%s\n' "$advance_request" |
      post_json "/internal/v2/kst/advance"
  )
  printf '%s\n' "$advance_response" | jq .

  status=$(printf '%s\n' "$advance_response" | jq -er '.status')
  case "$status" in
    completed)
      echo
      echo "Experiment completed."
      exit 0
      ;;
    in_progress)
      posterior=$(printf '%s\n' "$advance_response" | jq -e '.posterior')
      candidate_id=$(
        printf '%s\n' "$advance_response" |
          jq -er '.next_candidate.candidate_id'
      )
      candidate_node=$(
        printf '%s\n' "$advance_response" |
          jq -er '.next_candidate.node'
      )
      candidates=$remaining_candidates
      response_count=$((response_count + 1))
      ;;
    *)
      echo "Unexpected assessment status: $status" >&2
      exit 1
      ;;
  esac
done
