# PROJECT_101: SMOKELAND-PYTHON

## What is this?
Python tool that **auto-generates CloudWatch dashboards** for Lambda fleets. Groups functions by name-regex + tags, handles the 500KB dashboard-body limit.

## Why it matters
Manually clicking 100 widgets in the CloudWatch UI is soul-crushing. Generating them from code means every new Lambda shows up on the dashboard automatically.

## What you did
- List all Lambdas via boto3, group by regex/tags
- Build the dashboard body JSON (widgets: invocations, errors, duration)
- Split into multiple dashboards when the 500KB limit is hit

## Interview one-liner
"I wrote our Lambda dashboard generator — auto-groups functions by tag/regex, auto-splits at CloudWatch's 500KB limit."

## Key concepts
- **CloudWatch dashboard body** is a JSON blob, capped at 500KB
- **Widget types** — metric, text, log-insights
- **Metric math** to overlay a series across many functions
