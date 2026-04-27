# Lambda Performance Monitoring Dashboard Generator

A standalone Python 3 CLI that **auto-generates a CloudWatch dashboard covering every Lambda function in your account**, grouped by service/component (inferred from naming conventions and tags). Creates, updates, or deletes a single dashboard named `LambdaPerformanceMonitoring` from a one-shot script — no IaC, no manual widget editing.

## Highlights

- **Discovers all Lambdas automatically** — paginates `lambda:ListFunctions`, builds the widget layout on the fly.
- **Smart grouping** — regex-matches function names (`service-*`, `*-service`, `*-lambda`) and falls back to `Tags.Service` / `Tags.Component` for accurate service sections.
- **Summary + per-service sections** — the dashboard opens with "Total Invocations", "Total Errors", "Top 10 by Duration (p90)", "Top 10 by Errors", then drills into each service with **Invocations/Errors/Throttles**, **Duration p50/p90/p99**, and **Concurrency** widgets per function (4 functions per row).
- **Handles CloudWatch's 500 KB limit** — checks the serialised JSON size and, if it approaches the cap, auto-trims each service to its top 10 functions.
- **Exponential-backoff retries** — the shared `with_retries` wrapper handles `Throttling` responses from CloudWatch/Lambda gracefully.
- **Interactive** — menu prompts the user to Create/Update, Delete, or Exit; confirms destructive actions.

## Architecture

```
 AWS Lambda (all functions in region)
          │
          ▼ list_functions (paginated)
 Python script
   ├─ group_functions_by_service(name regex + Tags)
   ├─ create_summary_widgets(invocations, errors, top-10 duration, top-10 errors)
   ├─ create_service_section_widgets(per function: invocations/errors/duration/concurrency)
   └─ size-guard (<500 KB) → trim to top 10 per service if needed
          │
          ▼ put_dashboard("LambdaPerformanceMonitoring")
 CloudWatch Dashboard
```

## Tech stack

- **Language:** Python 3
- **Libraries:** `boto3`, `botocore`, `logging`, `re`, `collections.defaultdict`
- **AWS services:** CloudWatch Dashboards, Lambda (read-only), CloudWatch metrics (`AWS/Lambda`)

## Repository layout

```
@SMOKELAND-PYTHON/
├── README.md
├── .gitignore
└── script.py      # lambda_dashboard.py — dashboard generator CLI
```

## How it works

1. `get_all_lambda_functions()` — paginated `list_functions` across the current region.
2. `group_functions_by_service(functions)` — regex-match naming patterns; prefer `Tags.Service` when present.
3. `create_summary_widgets(functions)` — four summary widgets (invocations, errors, top-10 duration, top-10 errors) + a markdown banner.
4. `create_service_section_widgets(service, funcs)` — per-service header + 4 funcs-per-row grid of invocation/error, duration p50/p90/p99, and concurrency widgets.
5. `create_dashboard(functions)` — stitches widgets into one body, checks size, calls `put_dashboard`.
6. `main()` — interactive menu: create/update, delete, exit.

## Prerequisites

- Python 3.8+
- `boto3` installed (`pip install boto3`)
- AWS credentials with `lambda:ListFunctions`, `cloudwatch:PutDashboard`, `cloudwatch:GetDashboard`, `cloudwatch:DeleteDashboards`

## Usage

```bash
python script.py
```

Then follow the interactive prompts (Create/Update, Delete, Exit) and confirm with `yes`.

Once done, the dashboard URL is printed:

```
https://<region>.console.aws.amazon.com/cloudwatch/home#dashboards:name=LambdaPerformanceMonitoring
```

## Notes

- The script targets the default region — set `AWS_DEFAULT_REGION` (or `AWS_REGION`) before running to target a different one. Dashboards are regional.
- For multi-region visibility, run the script in each region or extend it to iterate across regions and emit separate dashboards.
- Demonstrates: automated CloudWatch dashboard generation, metric-math `SORT(METRICS(), ..., 10)` for top-N charts, CloudWatch payload size handling, boto3 paginators, `ClientError` retry loops.
