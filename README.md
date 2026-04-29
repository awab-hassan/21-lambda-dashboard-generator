# lambda-dashboard-generator

A Python 3 CLI that auto-generates a CloudWatch dashboard covering every Lambda function in your AWS account, grouped by service. Creates, updates, or deletes a single dashboard named `LambdaPerformanceMonitoring` from a one-shot script — no IaC, no manual widget editing.

## How It Works

```
Lambda (all functions in region)
    |
    | list_functions (paginated)
    v
Python script
    +-- group_functions_by_service()   regex on name + Tags.Service fallback
    +-- create_summary_widgets()       total invocations, errors, top-10 duration, top-10 errors
    +-- create_service_section_widgets() per function: invocations/errors/duration/concurrency
    +-- size guard (<500 KB)           trims to top 10 per service if needed
    |
    | put_dashboard()
    v
CloudWatch Dashboard: LambdaPerformanceMonitoring
```

## Dashboard Layout

**Summary section** (account-wide):
- Total Invocations
- Total Errors
- Top 10 by Duration (p90)
- Top 10 by Errors

**Per-service sections** (4 functions per row):
- Invocations / Errors / Throttles
- Duration p50 / p90 / p99
- Concurrency

Services are inferred by regex matching function names (`service-*`, `*-service`, `*-lambda`) with `Tags.Service` / `Tags.Component` used as fallback.

## Stack

Python 3 · boto3 · AWS CloudWatch Dashboards · Lambda (read-only)

## Repository Layout

```
lambda-dashboard-generator/
├── script.py       # Dashboard generator CLI
├── .gitignore
└── README.md
```

## Prerequisites

- Python 3.8+
- `pip install boto3`
- AWS credentials with:
  - `lambda:ListFunctions`
  - `cloudwatch:PutDashboard`
  - `cloudwatch:GetDashboard`
  - `cloudwatch:DeleteDashboards`

## Usage

```bash
python script.py
```

Follow the interactive prompts: Create/Update, Delete, or Exit. Destructive actions require confirmation.

On completion the dashboard URL is printed:

```
https://<region>.console.aws.amazon.com/cloudwatch/home#dashboards:name=LambdaPerformanceMonitoring
```

## Notes

- Targets the default AWS region. Set `AWS_DEFAULT_REGION` before running to target a specific region. Dashboards are regional.
- For multi-region coverage, run the script once per region or extend it to iterate regions and emit separate dashboards.
- Handles CloudWatch's 500 KB dashboard size limit by auto-trimming each service section to its top 10 functions when the payload approaches the cap.
- API throttling is handled via exponential backoff retries on all CloudWatch and Lambda calls.
