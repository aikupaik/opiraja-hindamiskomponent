import http from "k6/http";
import { check, fail } from "k6";

const baseUrl = __ENV.PERF_BASE_URL;

if (!baseUrl) {
  fail("PERF_BASE_URL must be supplied through protected environment input");
}

export const options = {
  vus: 1,
  iterations: 1,
  thresholds: {
    http_req_failed: ["rate==0"],
    http_req_duration: ["p(95)<3000"],
  },
};

export default function () {
  const requestId = `perf-static-edge-${__VU}-${__ITER}`;
  const response = http.get(`${baseUrl}/`, {
    headers: { "X-Request-ID": requestId },
    tags: { scenario: "static-edge-smoke" },
  });

  check(response, {
    "returns successful HTML": (value) => value.status === 200,
    "returns a request identifier": (value) => Boolean(value.headers["X-Request-Id"]),
  });
}
