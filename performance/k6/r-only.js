import http from "k6/http";
import { check, fail } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";
import { SharedArray } from "k6/data";

const fixturePaths = {
  "3-chain": "../fixtures/r/3-chain.json",
  "10-chain": "../fixtures/r/10-chain.json",
  "10-independent": "../fixtures/r/10-independent.json",
};

const baseUrl = requiredBaseUrl(__ENV.PERF_R_BASE_URL);
const runId = requiredRunId(__ENV.PERF_RUN_ID);
const shape = choice(
  __ENV.PERF_R_SHAPE || "3-chain",
  "PERF_R_SHAPE",
  Object.keys(fixturePaths),
);
const loadMode = choice(
  __ENV.PERF_R_LOAD_MODE || "smoke",
  "PERF_R_LOAD_MODE",
  ["smoke", "closed", "open"],
);
const fixture = new SharedArray(`r-v2-${shape}`, function () {
  return [JSON.parse(open(fixturePaths[shape]))];
})[0];

const integrityFailureRate = new Rate("r_integrity_failure_rate");
const unexpectedFailureRate = new Rate("r_unexpected_failure_rate");
const completedFlows = new Counter("r_completed_flows");
const flowDuration = new Trend("r_flow_duration", true);
const operationDuration = new Trend("r_operation_duration", true);
const operationRequests = {
  model: new Counter("r_model_requests"),
  select: new Counter("r_select_requests"),
  advance: new Counter("r_advance_requests"),
};

export const options = {
  scenarios: {
    r_only: scenario(loadMode),
  },
  summaryTrendStats: ["min", "med", "avg", "p(90)", "p(95)", "p(99)", "max"],
  thresholds: {
    dropped_iterations: ["count==0"],
    http_req_failed: ["rate<0.01"],
    http_req_duration: [
      "p(95)<=3000",
      "p(99)<=5000",
      { threshold: "p(99)<=10000", abortOnFail: true, delayAbortEval: "2m" },
    ],
    r_integrity_failure_rate: [
      { threshold: "rate==0", abortOnFail: true },
    ],
    r_unexpected_failure_rate: [
      "rate<0.01",
      { threshold: "rate<=0.05", abortOnFail: true, delayAbortEval: "30s" },
    ],
    ...operationThresholds(),
  },
};

export default function () {
  const startedAt = Date.now();
  const flowId = `${runId}-r-v2-${shape}-${loadMode}-${__VU}-${__ITER}`;

  const modelResponse = requestOperation("model", fixture.operations.model, flowId);
  if (modelResponse === null) {
    fail("R v2 model operation failed; dependent operations were skipped");
  }

  const selectRequest = {
    model: modelResponse.model,
    posterior: modelResponse.posterior,
    candidates: fixture.operations.select.request.candidates,
  };
  const selectResponse = requestOperation(
    "select",
    fixture.operations.select,
    flowId,
    selectRequest,
  );
  if (selectResponse === null) {
    fail("R v2 select operation failed; advance was skipped");
  }

  const administered = selectRequest.candidates.find(
    (candidate) => candidate.candidate_id === selectResponse.candidate_id,
  );
  if (administered === undefined) {
    integrityFailureRate.add(true, { operation: "select" });
    fail("R v2 select returned a candidate outside the supplied inventory");
  }

  const advanceRequest = {
    model: modelResponse.model,
    posterior: modelResponse.posterior,
    administered,
    response_correct: fixture.operations.advance.request.response_correct,
    response_count: fixture.operations.advance.request.response_count,
    remaining_candidates: selectRequest.candidates.filter(
      (candidate) => candidate.candidate_id !== administered.candidate_id,
    ),
  };
  const advanceResponse = requestOperation(
    "advance",
    fixture.operations.advance,
    flowId,
    advanceRequest,
  );
  if (advanceResponse === null) {
    fail("R v2 advance operation failed");
  }

  completedFlows.add(1);
  flowDuration.add(Date.now() - startedAt);
}

function requestOperation(operation, fixtureOperation, flowId, requestBody) {
  operationRequests[operation].add(1);
  const response = http.post(
    `${baseUrl}${fixtureOperation.path}`,
    JSON.stringify(requestBody === undefined ? fixtureOperation.request : requestBody),
    {
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-Request-ID": `${flowId}-${operation}`,
      },
      tags: {
        operation,
      },
      timeout: "15s",
    },
  );

  operationDuration.add(response.timings.duration, { operation });

  const statusOk = response.status === 200;
  const contentTypeOk = headerIncludes(response, "Content-Type", "application/json");
  const parsed = parseJson(response.body);
  const responseMatches = parsed !== null && deepEqual(parsed, fixtureOperation.expected_response);
  const contractOk = contentTypeOk && responseMatches;

  unexpectedFailureRate.add(!statusOk, { operation });
  integrityFailureRate.add(statusOk && !contractOk, { operation });

  check(
    response,
    {
      [`${operation} returns 200`]: () => statusOk,
      [`${operation} returns JSON`]: () => contentTypeOk && parsed !== null,
      [`${operation} matches the fixture`]: () => statusOk && responseMatches,
    },
    { operation },
  );

  return statusOk && contractOk ? parsed : null;
}

function scenario(mode) {
  const common = {
    exec: "default",
    tags: {
      component: "r",
      graph_shape: shape,
      load_mode: mode,
      test_stage: "r-only",
    },
  };

  if (mode === "smoke") {
    return {
      ...common,
      executor: "per-vu-iterations",
      vus: 1,
      iterations: 1,
      maxDuration: "2m",
    };
  }

  const duration = __ENV.PERF_R_DURATION || "10m";
  if (mode === "closed") {
    return {
      ...common,
      executor: "constant-vus",
      vus: positiveInteger(__ENV.PERF_R_VUS || "1", "PERF_R_VUS"),
      duration,
      gracefulStop: "30s",
    };
  }

  const rate = positiveInteger(__ENV.PERF_R_RATE || "1", "PERF_R_RATE");
  const preAllocatedVUs = positiveInteger(
    __ENV.PERF_R_PRE_ALLOCATED_VUS || String(rate),
    "PERF_R_PRE_ALLOCATED_VUS",
  );
  const maxVUs = positiveInteger(
    __ENV.PERF_R_MAX_VUS || String(Math.max(preAllocatedVUs, rate * 2)),
    "PERF_R_MAX_VUS",
  );
  if (maxVUs < preAllocatedVUs) {
    fail("PERF_R_MAX_VUS must be greater than or equal to PERF_R_PRE_ALLOCATED_VUS");
  }

  return {
    ...common,
    executor: "constant-arrival-rate",
    rate,
    timeUnit: "1s",
    duration,
    preAllocatedVUs,
    maxVUs,
    gracefulStop: "30s",
  };
}

function operationThresholds() {
  const thresholds = {};

  for (const operation of ["model", "select", "advance"]) {
    const selector = `{operation:${operation}}`;
    thresholds[`http_req_duration${selector}`] = ["p(95)<=3000", "p(99)<=5000"];
    thresholds[`http_req_failed${selector}`] = ["rate<0.01"];
  }

  return thresholds;
}

function parseJson(body) {
  try {
    return JSON.parse(body);
  } catch (_error) {
    return null;
  }
}

function deepEqual(actual, expected) {
  if (typeof actual === "number" && typeof expected === "number") {
    return Math.abs(actual - expected) <= 1e-12 * Math.max(1, Math.abs(expected));
  }

  if (actual === null || expected === null || typeof actual !== typeof expected) {
    return actual === expected;
  }

  if (Array.isArray(actual) || Array.isArray(expected)) {
    if (!Array.isArray(actual) || !Array.isArray(expected) || actual.length !== expected.length) {
      return false;
    }

    for (let index = 0; index < actual.length; index += 1) {
      if (!deepEqual(actual[index], expected[index])) {
        return false;
      }
    }

    return true;
  }

  if (typeof actual === "object") {
    const actualKeys = Object.keys(actual).sort();
    const expectedKeys = Object.keys(expected).sort();
    if (!deepEqual(actualKeys, expectedKeys)) {
      return false;
    }

    for (const key of actualKeys) {
      if (!deepEqual(actual[key], expected[key])) {
        return false;
      }
    }

    return true;
  }

  return actual === expected;
}

function requiredBaseUrl(value) {
  if (!value) {
    fail("PERF_R_BASE_URL must be supplied");
  }

  return value.replace(/\/+$/, "");
}

function requiredRunId(value) {
  if (!value || !/^perf-[a-zA-Z0-9._-]+$/.test(value)) {
    fail("PERF_RUN_ID must start with 'perf-' and contain only safe marker characters");
  }

  return value;
}

function positiveInteger(value, name) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) {
    fail(`${name} must be a positive integer`);
  }

  return parsed;
}

function choice(value, name, allowed) {
  if (!allowed.includes(value)) {
    fail(`${name} must be one of: ${allowed.join(", ")}`);
  }

  return value;
}

function headerIncludes(response, name, expectedValue) {
  const headerName = Object.keys(response.headers).find(
    (key) => key.toLowerCase() === name.toLowerCase(),
  );

  return (
    headerName !== undefined &&
    String(response.headers[headerName]).toLowerCase().includes(expectedValue.toLowerCase())
  );
}
