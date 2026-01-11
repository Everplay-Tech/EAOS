/**
 * K6 Configuration File
 *
 * Global configuration for k6 load testing.
 * Can be overridden by individual test files or CLI options.
 */

export const options = {
  // Cloud configuration (if using k6 Cloud)
  // cloud: {
  //   projectID: 'your-project-id',
  //   name: 'Roulette Kernel Load Tests',
  // },

  // Extension configuration
  // ext: {
  //   loadimpact: {
  //     projectID: 'your-project-id',
  //   },
  // },

  // Execution configuration
  scenarios: {
    // Default scenario
    default: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 10 },
        { duration: '1m', target: 10 },
        { duration: '30s', target: 0 },
      ],
      gracefulRampDown: '30s',
    },
  },

  // Global thresholds
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    http_req_failed: ['rate<0.01'],
    http_reqs: ['rate>10'],
    checks: ['rate>0.95'],
  },

  // Batch settings
  batch: 10,
  batchPerHost: 6,

  // HTTP settings
  http: {
    timeout: '30s',
    grace: '5s',
  },

  // Discard response bodies by default (saves memory)
  discardResponseBodies: false,

  // DNS settings
  dns: {
    ttl: '5m',
    select: 'first',
    policy: 'preferIPv4',
  },

  // User agent
  userAgent: 'K6LoadTest/1.0 (Roulette-Kernel)',

  // Tags applied to all metrics
  tags: {
    project: 'roulette-kernel',
    environment: 'test',
  },

  // System tags to include in metrics
  systemTags: [
    'proto',
    'subproto',
    'status',
    'method',
    'url',
    'name',
    'group',
    'check',
    'error',
    'tls_version',
  ],

  // Minimum iteration duration
  minIterationDuration: '1s',

  // No connection reuse (set to true for more realistic load)
  noConnectionReuse: false,

  // No VU connection reuse
  noVUConnectionReuse: false,

  // Throw errors on failed HTTP requests
  throw: false,
};
