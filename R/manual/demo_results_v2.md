1. Health check
{
  "status": "ok"
}

2. Create the v2 KST model
{
  "model": {
    "schema_version": 2,
    "method": "kst",
    "nodes": [
      "A",
      "B",
      "C"
    ],
    "knowledge_states": [
      [],
      ["A"],
      ["A", "B"],
      ["A", "B", "C"]
    ],
    "matrix": [
      [0, 0, 0],
      [1, 0, 0],
      [1, 1, 0],
      [1, 1, 1]
    ],
    "uniform_prior": [
      0.25,
      0.25,
      0.25,
      0.25
    ],
    "configuration": {
      "feedback_credible_mass": 0.9,
      "reliability_floor": {
        "maximum": 10,
        "minimum": 7,
        "multiplier": 1.5
      },
      "safety_cap": {
        "minimum_above_floor": 1,
        "node_multiplier": 2
      },
      "schema_version": 1,
      "stop_confidence": 0.8
    },
    "configuration_hash": "kst-config-v1:sha256:89b7af74a8eca453d36a3410e18f8c221000ea67cc06388418ec675de766c774",
    "reliability_floor": 7,
    "safety_cap": 8
  },
  "posterior": [
    0.25,
    0.25,
    0.25,
    0.25
  ]
}

3. Select the first candidate from the experiment inventory
{
  "candidate_id": "yp:102",
  "node": "B"
}

4. Answer each selected candidate correctly, without reuse

Answer 1: candidate=yp:102, node=B, correct=true
{
  "status": "in_progress",
  "posterior": [
    0.104166666666667,
    0.104166666666667,
    0.395833333333333,
    0.395833333333333
  ],
  "next_candidate": {
    "candidate_id": "yp:103",
    "node": "C"
  }
}

Answer 2: candidate=yp:103, node=C, correct=true
{
  "status": "in_progress",
  "posterior": [
    0.0494071146245061,
    0.0494071146245061,
    0.187747035573122,
    0.713438735177865
  ],
  "next_candidate": {
    "candidate_id": "yp:101",
    "node": "A"
  }
}

Answer 3: candidate=yp:101, node=A, correct=true
{
  "status": "completed",
  "posterior": [
    0.013493091537133,
    0.0512737478411056,
    0.1948402417962,
    0.740392918825561
  ],
  "profile": {
    "mastered": [
      "A",
      "B"
    ],
    "ready_to_learn": [],
    "uncertain_ahead": [
      "C"
    ],
    "uncertain_prerequisite": [],
    "not_yet": [],
    "summary": null,
    "stop_reason": "item_inventory_exhausted",
    "best_state_confidence": 0.740392918825561,
    "credible_mass": 0.935233160621761,
    "credible_state_count": 2,
    "confidence_limited": true
  }
}

Experiment completed.