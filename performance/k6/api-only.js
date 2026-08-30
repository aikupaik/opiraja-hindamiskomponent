import http from "k6/http";
import { check, fail } from "k6";
import { SharedArray } from "k6/data";
import { Counter, Rate, Trend } from "k6/metrics";

const fixturePaths = {
  "3-chain": "../fixtures/r/3-chain.json",
  "10-chain": "../fixtures/r/10-chain.json",
  "10-independent": "../fixtures/r/10-independent.json",
};

const baseUrl = requiredBaseUrl(__ENV.PERF_API_BASE_URL);
const runId = requiredRunId(__ENV.PERF_RUN_ID);
const orToken = requiredSecret(__ENV.PERF_OR_TOKEN, "PERF_OR_TOKEN");
const shape = choice(
  __ENV.PERF_API_SHAPE || "3-chain",
  "PERF_API_SHAPE",
  Object.keys(fixturePaths),
);
const workload = choice(
  __ENV.PERF_API_WORKLOAD || "routes",
  "PERF_API_WORKLOAD",
  ["routes", "session"],
);
const loadMode = choice(
  __ENV.PERF_API_LOAD_MODE || "smoke",
  "PERF_API_LOAD_MODE",
  ["smoke", "closed", "open"],
);
if (workload === "session" && loadMode === "open") {
  fail("PERF_API_LOAD_MODE=open is supported only for the routes workload");
}

const fixture = new SharedArray(`api-only-${shape}`, function () {
  return [JSON.parse(open(fixturePaths[shape]))];
})[0];
const expectedAnswerCount = fixture.operations.model.expected_response.model.reliability_floor;

const integrityFailureRate = new Rate("api_integrity_failure_rate");
const unexpectedFailureRate = new Rate("api_unexpected_failure_rate");
const completedFlows = new Counter("api_completed_flows");
const completedSessions = new Counter("api_completed_sessions");
const answerRequests = new Counter("api_answer_requests");
const flowDuration = new Trend("api_flow_duration", true);
const operationDuration = new Trend("api_operation_duration", true);

export const options = {
  scenarios: {
    api_only: scenario(workload, loadMode),
  },
  summaryTrendStats: ["min", "med", "avg", "p(90)", "p(95)", "p(99)", "max"],
  thresholds: {
    dropped_iterations: ["count==0"],
    "http_req_failed{phase:load}": ["rate<0.01"],
    "http_req_duration{phase:load}": [
      "p(95)<=3000",
      "p(99)<=5000",
      { threshold: "p(99)<=10000", abortOnFail: true, delayAbortEval: "2m" },
    ],
    api_integrity_failure_rate: [
      { threshold: "rate==0", abortOnFail: true },
    ],
    api_unexpected_failure_rate: [
      "rate<0.01",
      { threshold: "rate<=0.05", abortOnFail: true, delayAbortEval: "30s" },
    ],
    ...operationThresholds(),
  },
};

export function setup() {
  requestJson({
    method: "GET",
    path: "/api/v1/tests/00000000-0000-4000-8000-000000000001",
    token: "invalid-api-only-token",
    expectedStatus: 401,
    operation: "setup-invalid-token",
    flowId: "setup-invalid-token",
    phase: "setup",
    validate: (body) => {
      return body.error !== undefined && body.error.code === "invalid_token";
    },
  });
  if (workload !== "routes") {
    return null;
  }

  const active = createSession("setup-active", "setup-active");
  const completed = createSession("setup-completed", "setup-completed");
  let current = startSession(completed, "setup-completed-start", "setup");
  let lastPayload = null;
  for (let index = 0; index < expectedAnswerCount; index += 1) {
    if (current.status !== "active") {
      fail(`setup session completed after ${index} answers; expected ${expectedAnswerCount}`);
    }
    lastPayload = answerPayload(current);
    current = setupJsonRequest(
      "POST",
      `/api/v1/player/tests/${completed.testId}/answers`,
      completed.playerToken,
      lastPayload,
      200,
      `setup-completed-answer-${index + 1}`,
    );
  }
  if (current.status !== "completed" || lastPayload === null) {
    fail("setup session did not reach completed status");
  }
  assertCompletedShape(current, expectedAnswerCount, "setup completed response");

  return {
    active,
    completed: {
      ...completed,
      lastPayload,
      completedResponse: current,
    },
  };
}

export default function (data) {
  if (workload === "routes") {
    routeFlow(data);
    return;
  }
  sessionFlow();
}

function routeFlow(data) {
  if (data === null || data.active === undefined || data.completed === undefined) {
    integrityFailureRate.add(true, { operation: "route-flow" });
    fail("route workload setup data is unavailable");
  }
  const startedAt = Date.now();
  const flowId = flowIdentifier("routes");

  requestJson({
    method: "GET",
    path: "/health/live",
    expectedStatus: 200,
    operation: "live",
    flowId,
    validate: (body) => body.status === "ok",
  });
  requestJson({
    method: "GET",
    path: `/api/v1/tests/${data.active.testId}`,
    token: orToken,
    expectedStatus: 200,
    operation: "status-active",
    flowId,
    validate: (body) => body.status === "active",
  });
  requestJson({
    method: "POST",
    path: `/api/v1/player/tests/${data.active.testId}/start`,
    token: data.active.playerToken,
    expectedStatus: 200,
    operation: "start-active",
    flowId,
    validate: activeResponseIsValid,
  });
  answerRequests.add(1);
  requestJson({
    method: "POST",
    path: `/api/v1/player/tests/${data.completed.testId}/answers`,
    token: data.completed.playerToken,
    body: data.completed.lastPayload,
    expectedStatus: 200,
    operation: "answer-replay",
    flowId,
    validate: (body) => {
      return (
        completedResponseIsValid(body, expectedAnswerCount) &&
        deepEqual(body, data.completed.completedResponse)
      );
    },
  });

  completedFlows.add(1);
  flowDuration.add(Date.now() - startedAt, { workload: "routes" });
}

function sessionFlow() {
  const startedAt = Date.now();
  const flowId = flowIdentifier("session");
  const session = createSession(
    `vu-${__VU}-iteration-${__ITER}`,
    flowId,
    "load",
  );

  requestJson({
    method: "GET",
    path: `/api/v1/tests/${session.testId}`,
    token: orToken,
    expectedStatus: 200,
    operation: "status-active",
    flowId,
    validate: (body) => body.status === "active",
  });
  let current = requestJson({
    method: "POST",
    path: `/api/v1/player/tests/${session.testId}/start`,
    token: session.playerToken,
    expectedStatus: 200,
    operation: "start-active",
    flowId,
    validate: activeResponseIsValid,
  });
  const submissionIds = new Set();
  let lastPayload = null;
  for (let index = 0; index < expectedAnswerCount; index += 1) {
    if (!activeResponseIsValid(current)) {
      integrityFailureRate.add(true, { operation: "answer" });
      fail(`session stopped before expected answer ${index + 1}`);
    }
    lastPayload = answerPayload(current);
    if (submissionIds.has(lastPayload.submission_id)) {
      integrityFailureRate.add(true, { operation: "answer" });
      fail("session returned a duplicate submission ID");
    }
    submissionIds.add(lastPayload.submission_id);
    answerRequests.add(1);
    const finalAnswer = index + 1 === expectedAnswerCount;
    current = requestJson({
      method: "POST",
      path: `/api/v1/player/tests/${session.testId}/answers`,
      token: session.playerToken,
      body: lastPayload,
      expectedStatus: 200,
      operation: "answer",
      flowId: `${flowId}-${index + 1}`,
      validate: finalAnswer
        ? (body) => completedResponseIsValid(body, expectedAnswerCount)
        : activeResponseIsValid,
    });
  }

  if (lastPayload === null || !completedResponseIsValid(current, expectedAnswerCount)) {
    integrityFailureRate.add(true, { operation: "session-complete" });
    fail("session did not complete with the expected response shape");
  }
  const completedResponse = current;
  answerRequests.add(1);
  const replayed = requestJson({
    method: "POST",
    path: `/api/v1/player/tests/${session.testId}/answers`,
    token: session.playerToken,
    body: lastPayload,
    expectedStatus: 200,
    operation: "answer-replay",
    flowId,
    validate: (body) => deepEqual(body, completedResponse),
  });
  if (!deepEqual(replayed, completedResponse)) {
    integrityFailureRate.add(true, { operation: "answer-replay" });
    fail("answer replay changed completed state");
  }
  requestJson({
    method: "GET",
    path: `/api/v1/tests/${session.testId}`,
    token: orToken,
    expectedStatus: 200,
    operation: "status-completed",
    flowId,
    validate: (body) => body.status === "completed" && body.feedback !== undefined,
  });

  completedSessions.add(1);
  completedFlows.add(1);
  flowDuration.add(Date.now() - startedAt, { workload: "session" });
}

function createSession(marker, flowId, phase = "setup") {
  const parsed = requestJson({
    method: "POST",
    path: "/api/v1/tests",
    token: orToken,
    body: {
      user_id: `${runId}-${marker}`,
      learning_path_id: `${runId}-${marker}`,
      nodes: fixture.graph.nodes,
      relations: fixture.graph.relations,
      course: "API-only performance fixture",
      goal: `API-only ${shape}`,
    },
    expectedStatus: 201,
    operation: "create",
    flowId,
    phase,
    validate: (body) => {
      return (
        body.status === "active" &&
        body.missing_nodes !== undefined &&
        body.missing_nodes.length === 0 &&
        typeof body.test_id === "string" &&
        typeof body.player_url === "string"
      );
    },
  });
  const playerToken = tokenFromPlayerUrl(parsed.player_url);
  if (playerToken === null) {
    if (phase === "load") {
      integrityFailureRate.add(true, { operation: "create" });
    }
    fail("create response contains no player token fragment");
  }
  return { testId: parsed.test_id, playerToken };
}

function startSession(session, flowId, phase) {
  return setupJsonRequest(
    "POST",
    `/api/v1/player/tests/${session.testId}/start`,
    session.playerToken,
    undefined,
    200,
    flowId,
    phase,
  );
}

function requestJson({
  method,
  path,
  token,
  body,
  expectedStatus,
  operation,
  flowId,
  phase = "load",
  validate,
}) {
  const headers = {
    Accept: "application/json",
    "X-Request-ID": requestId(flowId, operation),
  };
  if (token !== undefined) {
    headers.Authorization = `Bearer ${token}`;
  }
  let serializedBody;
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    serializedBody = JSON.stringify(body);
  }
  const params = {
    headers,
    tags: {
      phase,
      operation,
      name: `${method} ${normalizedPath(operation)}`,
    },
    timeout: "15s",
    responseCallback: http.expectedStatuses(expectedStatus),
  };
  const response = http.request(method, `${baseUrl}${path}`, serializedBody, params);
  if (phase === "load") {
    operationDuration.add(response.timings.duration, { operation });
  }
  const parsed = parseJson(response.body);
  const statusOk = response.status === expectedStatus;
  const contentTypeOk = headerIncludes(response, "Content-Type", "application/json");
  const requestIdOk = headerIncludes(response, "X-Request-ID", headers["X-Request-ID"]);
  const contractOk = parsed !== null && validate(parsed);

  if (phase === "load") {
    unexpectedFailureRate.add(!statusOk, { operation });
    integrityFailureRate.add(statusOk && (!contentTypeOk || !requestIdOk || !contractOk), {
      operation,
    });
    check(
      response,
      {
        [`${operation} returns ${expectedStatus}`]: () => statusOk,
        [`${operation} returns JSON`]: () => contentTypeOk && parsed !== null,
        [`${operation} preserves request ID`]: () => requestIdOk,
        [`${operation} matches contract`]: () => statusOk && contractOk,
      },
      { operation },
    );
  }
  if (!statusOk || !contentTypeOk || !requestIdOk || !contractOk || parsed === null) {
    fail(`${phase} ${operation} request failed validation with status ${response.status}`);
  }
  return parsed;
}

function setupJsonRequest(
  method,
  path,
  token,
  body,
  expectedStatus,
  operation,
  phase = "setup",
) {
  return requestJson({
    method,
    path,
    token,
    body,
    expectedStatus,
    operation,
    flowId: operation,
    phase,
    validate: (value) => typeof value.status === "string",
  });
}

function activeResponseIsValid(body) {
  return (
    body !== null &&
    body.status === "active" &&
    body.question !== undefined &&
    typeof body.question.submission_id === "string" &&
    Number.isInteger(body.question.item_id) &&
    Array.isArray(body.question.options) &&
    body.question.options.length >= 2 &&
    body.question.options.every(
      (option) => typeof option.id === "string" && typeof option.text === "string",
    )
  );
}

function completedResponseIsValid(body, answerCount) {
  return (
    body !== null &&
    body.status === "completed" &&
    body.feedback !== undefined &&
    Array.isArray(body.question_results) &&
    body.question_results.length === answerCount
  );
}

function assertCompletedShape(body, answerCount, description) {
  if (!completedResponseIsValid(body, answerCount)) {
    fail(`${description} is invalid`);
  }
}

function answerPayload(active) {
  return {
    submission_id: active.question.submission_id,
    option_id: active.question.options[0].id,
  };
}

function scenario(selectedWorkload, mode) {
  const common = {
    exec: "default",
    tags: {
      component: "api",
      graph_shape: shape,
      load_mode: mode,
      test_stage: "api-only",
      workload: selectedWorkload,
    },
  };
  if (mode === "smoke") {
    return {
      ...common,
      executor: "per-vu-iterations",
      vus: 1,
      iterations: 1,
      maxDuration: "5m",
    };
  }

  const vus = positiveInteger(__ENV.PERF_API_VUS || "1", "PERF_API_VUS");
  if (selectedWorkload === "session") {
    return {
      ...common,
      executor: "per-vu-iterations",
      vus,
      iterations: 1,
      maxDuration: __ENV.PERF_API_MAX_DURATION || "10m",
    };
  }

  const duration = __ENV.PERF_API_DURATION || "10m";
  if (mode === "closed") {
    return {
      ...common,
      executor: "constant-vus",
      vus,
      duration,
      gracefulStop: "30s",
    };
  }

  const rate = positiveInteger(__ENV.PERF_API_RATE || "1", "PERF_API_RATE");
  const preAllocatedVUs = positiveInteger(
    __ENV.PERF_API_PRE_ALLOCATED_VUS || String(vus),
    "PERF_API_PRE_ALLOCATED_VUS",
  );
  const maxVUs = positiveInteger(
    __ENV.PERF_API_MAX_VUS || String(preAllocatedVUs * 2),
    "PERF_API_MAX_VUS",
  );
  if (maxVUs < preAllocatedVUs) {
    fail("PERF_API_MAX_VUS must be greater than or equal to PERF_API_PRE_ALLOCATED_VUS");
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
  const operations = workload === "routes"
    ? ["live", "status-active", "start-active", "answer-replay"]
    : ["create", "status-active", "start-active", "answer", "answer-replay", "status-completed"];
  for (const operation of operations) {
    const selector = `{phase:load,operation:${operation}}`;
    thresholds[`http_req_duration${selector}`] = ["p(95)<=3000", "p(99)<=5000"];
    thresholds[`http_req_failed${selector}`] = ["rate<0.01"];
  }
  return thresholds;
}

function normalizedPath(operation) {
  const values = {
    live: "/health/live",
    create: "/api/v1/tests",
    "status-active": "/api/v1/tests/:id",
    "status-completed": "/api/v1/tests/:id",
    "start-active": "/api/v1/player/tests/:id/start",
    answer: "/api/v1/player/tests/:id/answers",
    "answer-replay": "/api/v1/player/tests/:id/answers",
  };
  return values[operation] || operation;
}

function tokenFromPlayerUrl(value) {
  if (typeof value !== "string") {
    return null;
  }
  const marker = "#token=";
  const index = value.indexOf(marker);
  return index === -1 ? null : value.slice(index + marker.length);
}

function flowIdentifier(prefix) {
  return `${runId.slice(0, 48)}-${prefix}-vu${__VU}-iter${__ITER}`;
}

function requestId(flowId, operation) {
  const vu = typeof __VU === "undefined" ? 0 : __VU;
  const iteration = typeof __ITER === "undefined" ? 0 : __ITER;
  const suffix = `${operation}-vu${vu}-i${iteration}`;
  return `${flowId.slice(0, Math.max(1, 127 - suffix.length))}-${suffix}`;
}

function parseJson(body) {
  try {
    return JSON.parse(body);
  } catch (_error) {
    return null;
  }
}

function deepEqual(actual, expected) {
  if (actual === null || expected === null || typeof actual !== typeof expected) {
    return actual === expected;
  }
  if (Array.isArray(actual) || Array.isArray(expected)) {
    if (!Array.isArray(actual) || !Array.isArray(expected) || actual.length !== expected.length) {
      return false;
    }
    return actual.every((value, index) => deepEqual(value, expected[index]));
  }
  if (typeof actual === "object") {
    const actualKeys = Object.keys(actual).sort();
    const expectedKeys = Object.keys(expected).sort();
    return (
      deepEqual(actualKeys, expectedKeys) &&
      actualKeys.every((key) => deepEqual(actual[key], expected[key]))
    );
  }
  return actual === expected;
}

function requiredBaseUrl(value) {
  if (!value) {
    fail("PERF_API_BASE_URL must be supplied");
  }
  return value.replace(/\/+$/, "");
}

function requiredRunId(value) {
  if (!value || !/^perf-[A-Za-z0-9._-]+$/.test(value)) {
    fail("PERF_RUN_ID must start with 'perf-' and contain only safe marker characters");
  }
  return value;
}

function requiredSecret(value, name) {
  if (!value) {
    fail(`${name} must be supplied through protected environment input`);
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
    String(response.headers[headerName]).toLowerCase().includes(String(expectedValue).toLowerCase())
  );
}
