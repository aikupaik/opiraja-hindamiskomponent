1. Health check

```
{
  "status": "ok"
}
```

2. Create the KST model

```
{
  "model": {
    "schema_version": 1,
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
    "beta": [
      0.1,
      0.15,
      0.2
    ],
    "eta": [
      0.2,
      0.25,
      0.3
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
    "configuration_hash": "kst-config-v1:sha256:89b7af74a8eca453d36a3410e18f8c221000ea67cc06388418ec675de766c774"
  },
  "posterior": [
    0.25,
    0.25,
    0.25,
    0.25
  ],
  "next_node": "B"
}
```

3. Answer each selected node correctly until the assessment completes

Answer 1: node=B, correct=true

```
{
  "status": "in_progress",
  "posterior": [
    0.113636363636364,
    0.113636363636364,
    0.386363636363636,
    0.386363636363636
  ],
  "next_node": "C"
}
```

Answer 2: node=C, correct=true

```
{
  "status": "in_progress",
  "posterior": [
    0.0691244239631339,
    0.0691244239631339,
    0.235023041474654,
    0.626728110599078
  ],
  "next_node": "C"
}
```

Answer 3: node=C, correct=true

```
{
  "status": "in_progress",
  "posterior": [
    0.0338091660405711,
    0.0338091660405711,
    0.114951164537941,
    0.817430503380916
  ],
  "next_node": "C"
}
```

Answer 4: node=C, correct=true

```
{
  "status": "in_progress",
  "posterior": [
    0.0143114597688965,
    0.0143114597688965,
    0.0486589632142477,
    0.922718117247959
  ],
  "next_node": "C"
}
```

Answer 5: node=C, correct=true

```
{
  "status": "in_progress",
  "posterior": [
    0.00563917626254894,
    0.00563917626254894,
    0.0191731992926662,
    0.969548448182236
  ],
  "next_node": "C"
}
```

Answer 6: node=C, correct=true

```
{
  "status": "in_progress",
  "posterior": [
    0.00215571922067646,
    0.00215571922067646,
    0.0073294453502999,
    0.988359116208347
  ],
  "next_node": "C"
}
```

Answer 7: node=C, correct=true

```
{
  "status": "completed",
  "posterior": [
    0.000814319330689833,
    0.000814319330689833,
    0.00276868572434541,
    0.995602675614275
  ],
  "profile": {
    "mastered": [
      "A",
      "B",
      "C"
    ],
    "ready_to_learn": [],
    "uncertain_ahead": [],
    "uncertain_prerequisite": [],
    "not_yet": [],
    "summary": "Teadsid kõike! Võta uus õpiväljund.",
    "stop_reason": "natural",
    "best_state_confidence": 0.995602675614275,
    "credible_mass": 0.995602675614275,
    "credible_state_count": 1
  }
}
```

Assessment completed.
