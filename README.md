# Tool Invocation Flow Assessment

## Project Overview
This project implements a structured tool-invocation pipeline for an AI agent. It validates requests, selects a registered tool, authorizes the caller, validates arguments, executes the handler, validates the output, and returns a controlled result.

The example tool is `order.lookup`, backed by a local sample order repository. The project demonstrates typed contracts, role-based access control, safe failure handling, rate limiting, idempotency, bounded timeout retries, structured logs, and reproducible evidence.

## Architecture
```text
Incoming tool call
  -> Request envelope validation
  -> Registered tool selection
  -> Principal / role authorization
  -> Tool argument validation
  -> Rate limit + idempotency checks
  -> Handler execution with bounded timeout retry
  -> Output schema validation
  -> ToolResult + structured log + trace
```

## Project Structure
```text
src/
  contracts.py
  dispatcher.py
  observability.py
  order_repository.py
  registry.py
  reliability.py
schemas/
tests/
  conftest.py
  test_task1_contract_registry.py
  test_task2_invocation_flow.py
  test_task3_security_failures.py
  test_task4_reliability.py
  test_task4_integration.py
traces/
evidence/
generate_evidence.py
requirements.txt
README.md
```

## Task Implementation

### Task 1 — Tool Contract and Registry
Pydantic models define the invocation envelope, order lookup input/output, result statuses, and next actions. The registry describes the `order.lookup` tool, its version, schemas, handler, access type, and permitted roles.

### Task 2 — Invocation Flow
The dispatcher validates the request envelope, selects a registered tool, authorizes the caller, validates arguments, invokes the handler, validates the output, and returns a structured `ToolResult`. A local repository supplies deterministic sample order data.

### Task 3 — Security and Failure Handling
Malformed calls and invalid order identifiers are rejected. Unauthorized callers are denied before handler execution. Unknown tools and orders return controlled statuses. Timeout and unexpected handler failures are mapped to safe responses without exposing internal exception messages.

### Task 4 — Reliability and Observability
The project includes structured JSON log records, a sliding-window rate limiter, request fingerprints, an in-memory idempotency store, and bounded retries that retry only `TimeoutError`. Integration tests cover repeated requests, request-ID conflicts, rate limiting, timeout recovery, retry exhaustion, and non-timeout failures.

### Task 5 — Evidence and Operator Report
`generate_evidence.py` creates four scenario traces and `evidence/operator_report.json`: success, authorization denial, provider/handler failure, and timeout recovery. The report compares actual and expected statuses and records implementation limitations.

## Verification
Latest reported full test run:
```text
52 passed in 0.18s
```

Run from the project root:
```cmd
python -m pytest -q
python generate_evidence.py
python -m json.tool evidence\operator_report.json
python -m pytest -v > evidence\full_test_output.txt 2>&1
```

## Evidence Artifacts
- `evidence/task1_test_output.txt` — contracts and registry tests
- `evidence/task2_test_output.txt` and `task2_demo_output.txt` — invocation flow
- `evidence/task3_test_output.txt` — security and failure handling
- `evidence/task4_test_output.txt` and `task4_integration_output.txt` — reliability tests
- `evidence/full_test_output.txt` — full regression suite
- `evidence/operator_report.json` — scenario status comparison and limitations
- `traces/task5_success.json` — successful lookup
- `traces/task5_denied.json` — authorization denial
- `traces/task5_provider_failure.json` — controlled handler failure
- `traces/task5_timeout_recovery.json` — timeout recovery

## Limitations and Future Improvements
Rate-limit and idempotency state are in-memory and process-local. Concurrent requests with the same request ID are not atomically reserved. The sample repository is not a live order service. A production deployment should use shared durable storage, atomic deduplication, provider-boundary timeouts, and operational metrics/alerts. Retry behavior should remain restricted to operations known to be safe to retry.

## Reflection (approximately 300 words)
Building this assessment helped me understand that tool invocation is more than calling a function after an LLM produces arguments. A dependable invocation flow needs clear contracts, controlled tool selection, authorization, validation, execution, and an observation that can be traced and tested. Separating these stages made it easier to reason about failures and test whether a handler was prevented from running when a request was malformed or unauthorized.

The contract and registry work showed the value of explicit input and output models. Rather than trusting arbitrary arguments, the dispatcher validates the request envelope and tool-specific input before execution, then validates the handler output. The security tests reinforced that internal exception messages should not be returned to callers. Errors need stable statuses and useful next actions without leaking private implementation details.

The reliability work introduced additional concerns. Rate limiting helps control request volume, while request fingerprints and idempotency checks can prevent accidental repeated execution. Bounded timeout retries can recover from transient failures, but retrying indiscriminately is unsafe, so this implementation retries only timeouts and defaults to one attempt. Structured JSON logs and scenario traces make behavior easier to inspect after a run.

The test failures during integration were useful because they exposed compatibility problems that isolated unit tests did not catch. The existing result model required dictionary data, and the original invocation trace expected a stable sequence of stages. Fixing these issues and rerunning the full suite demonstrated why regression tests matter when adding cross-cutting reliability features.

The main limitation is that the rate limiter and idempotency store are in-memory and process-local. They are appropriate for this learning assessment but would not be sufficient for a multi-worker production service. My next improvement would be shared durable storage and atomic request reservation, followed by latency and status metrics. Overall, this project strengthened my understanding of safe, testable, and observable tool-calling systems.
