import http from "k6/http";
import { check, fail } from "k6";

const baseUrl = requiredBaseUrl(__ENV.PERF_BASE_URL);
const vus = positiveInteger(__ENV.PERF_EDGE_VUS || "1", "PERF_EDGE_VUS");
const playerPath = "/test/perf-static-edge";

export const options = {
  scenarios: {
    static_edge: {
      executor: "per-vu-iterations",
      vus,
      iterations: 1,
      maxDuration: "2m",
      tags: { scenario: "static-edge" },
    },
  },
  summaryTrendStats: ["min", "med", "avg", "p(90)", "p(95)", "p(99)", "max"],
  thresholds: {
    checks: ["rate==1"],
    http_req_failed: ["rate==0"],
    http_req_duration: ["p(95)<3000"],
    ...staticEdgeRouteThresholds(),
  },
};

export default function () {
  loadPageAndAssets("admin", "/", "/assets/");
  loadPageAndAssets("player", playerPath, "/test/assets/");
}

function loadPageAndAssets(page, pagePath, assetPrefix) {
  const pageResponse = http.get(`${baseUrl}${pagePath}`, requestParams(page, "html", 0));

  check(pageResponse, {
    [`${page} HTML returns 200`]: (response) => response.status === 200,
    [`${page} HTML is HTML`]: (response) => headerIncludes(response, "Content-Type", "text/html"),
    [`${page} HTML has request ID`]: (response) => hasHeader(response, "X-Request-ID"),
  });

  const assetPaths = discoverAssets(pageResponse.body, assetPrefix);
  check(assetPaths, {
    [`${page} HTML discovers JS and CSS assets`]: (paths) =>
      paths.some((path) => path.endsWith(".js")) && paths.some((path) => path.endsWith(".css")),
  });

  for (let index = 0; index < assetPaths.length; index += 1) {
    const assetPath = assetPaths[index];
    const assetType = assetPath.endsWith(".css") ? "css" : "js";
    const assetResponse = http.get(
      `${baseUrl}${assetPath}`,
      requestParams(page, assetType, index + 1),
    );

    check(assetResponse, {
      [`${page} ${assetType} asset returns 200`]: (response) => response.status === 200,
      [`${page} ${assetType} asset has content type`]: (response) =>
        hasHeader(response, "Content-Type"),
      [`${page} ${assetType} asset is gzip encoded`]: (response) =>
        headerIncludes(response, "Content-Encoding", "gzip"),
      [`${page} ${assetType} asset varies by encoding`]: (response) =>
        headerIncludes(response, "Vary", "Accept-Encoding"),
      [`${page} ${assetType} asset is immutable`]: (response) =>
        headerIncludes(response, "Cache-Control", "immutable"),
      [`${page} ${assetType} asset has request ID`]: (response) =>
        hasHeader(response, "X-Request-ID"),
    });
  }
}

function requestParams(page, resource, sequence) {
  return {
    headers: {
      "X-Request-ID": `perf-static-edge-${__VU}-${__ITER}-${page}-${resource}-${sequence}`,
      "Accept-Encoding": "gzip",
    },
    tags: {
      edge_page: page,
      edge_resource: resource,
    },
  };
}

function discoverAssets(html, prefix) {
  const attributePattern = /(?:src|href)=["']([^"']+)["']/gi;
  const paths = [];
  const seen = {};
  let match;

  while ((match = attributePattern.exec(html)) !== null) {
    const path = match[1];
    if (
      path.startsWith(prefix) &&
      (path.endsWith(".js") || path.endsWith(".css")) &&
      !seen[path]
    ) {
      seen[path] = true;
      paths.push(path);
    }
  }

  return paths;
}

function requiredBaseUrl(value) {
  if (!value) {
    fail("PERF_BASE_URL must be supplied through protected environment input");
  }

  return value.replace(/\/+$/, "");
}

function positiveInteger(value, name) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 1) {
    fail(`${name} must be a positive integer`);
  }

  return parsed;
}

function hasHeader(response, name) {
  return Object.keys(response.headers).some((key) => key.toLowerCase() === name.toLowerCase());
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

function staticEdgeRouteThresholds() {
  const thresholds = {};

  for (const page of ["admin", "player"]) {
    for (const resource of ["html", "js", "css"]) {
      const tagSelector = `{edge_page:${page},edge_resource:${resource}}`;
      thresholds[`http_req_duration${tagSelector}`] = ["p(95)<3000"];
      thresholds[`http_req_failed${tagSelector}`] = ["rate==0"];
    }
  }

  return thresholds;
}
