#!/usr/bin/env python3
"""
Lambda Performance Monitoring Dashboard Generator

This script creates, updates, or deletes a CloudWatch dashboard that displays performance metrics
for all Lambda functions in your AWS account, organized by service/component.

Usage:
    python lambda_dashboard.py

The script will prompt for user confirmation before taking any action.
"""

import boto3
import json
import logging
import time
from botocore.exceptions import ClientError
from collections import defaultdict
import re

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set up AWS clients
lambda_client = boto3.client('lambda')
cloudwatch_client = boto3.client('cloudwatch')

# Dashboard configuration
DASHBOARD_NAME = "LambdaPerformanceMonitoring"
METRICS_PERIOD = 300  # 5 minutes, in seconds
FUNCTIONS_PER_ROW = 4
DASHBOARD_WIDTH = 24  # CloudWatch dashboard width in grid units

# Timeouts and retries for API throttling
MAX_RETRIES = 5
RETRY_DELAY_BASE = 1  # seconds

def get_all_lambda_functions():
    """
    Retrieve all Lambda functions in the account, handling pagination.
    """
    functions = []
    paginator = lambda_client.get_paginator('list_functions')
    
    try:
        for page in paginator.paginate():
            functions.extend(page['Functions'])
        logger.info(f"Retrieved {len(functions)} Lambda functions")
        return functions
    except ClientError as e:
        logger.error(f"Error retrieving Lambda functions: {e}")
        raise

def with_retries(func, *args, **kwargs):
    """
    Execute a function with exponential backoff retries for API throttling.
    """
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except ClientError as e:
            if e.response['Error']['Code'] == 'Throttling' and attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                logger.warning(f"API throttling detected, retrying in {delay} seconds...")
                time.sleep(delay)
            else:
                raise
    return None

def group_functions_by_service(functions):
    """
    Group Lambda functions by service or component based on naming conventions.
    """
    service_groups = defaultdict(list)
    
    for function in functions:
        name = function['FunctionName']
        
        # Extract service/component from function name
        service = "Other"
        
        # Common patterns for function naming: service-name-function, service_name_function, etc.
        patterns = [
            r'^([a-zA-Z0-9]+)[-_]',  # service-* or service_*
            r'^([a-zA-Z0-9]+)-service',  # *-service
            r'([a-zA-Z0-9]+)-lambda',  # *-lambda
        ]
        
        for pattern in patterns:
            match = re.match(pattern, name)
            if match:
                service = match.group(1).lower()
                break
                
        # Use tags if available for more accurate grouping
        if 'Tags' in function:
            tags = function['Tags']
            if 'Service' in tags:
                service = tags['Service']
            elif 'Component' in tags:
                service = tags['Component']
        
        service_groups[service].append(function)
    
    return service_groups

def create_summary_widgets(functions):
    """
    Create summary widgets for the dashboard.
    """
    widgets = []
    
    # Overall invocation count
    widgets.append({
        "type": "metric",
        "width": 12,
        "height": 6,
        "properties": {
            "view": "timeSeries",
            "stacked": False,
            "metrics": [
                [ "AWS/Lambda", "Invocations", "FunctionName", "*", { "stat": "Sum" } ]
            ],
            "region": boto3.session.Session().region_name,
            "title": "Total Lambda Invocations",
            "period": METRICS_PERIOD
        }
    })
    
    # Aggregate error rates
    widgets.append({
        "type": "metric",
        "width": 12,
        "height": 6,
        "properties": {
            "view": "timeSeries",
            "stacked": False,
            "metrics": [
                [ "AWS/Lambda", "Errors", "FunctionName", "*", { "stat": "Sum" } ]
            ],
            "region": boto3.session.Session().region_name,
            "title": "Total Lambda Errors",
            "period": METRICS_PERIOD
        }
    })
    
    # Top 10 functions by duration (p90)
    widgets.append({
        "type": "metric",
        "width": 12,
        "height": 8,
        "properties": {
            "view": "timeSeries",
            "stacked": False,
            "metrics": [
                [ { "expression": "SORT(METRICS(), MAX, 10)", "label": "Top 10 by Duration", "id": "e1" } ]
            ] + [["AWS/Lambda", "Duration", "FunctionName", function["FunctionName"], { "stat": "p90", "visible": False }] 
                for function in functions[:50]],  # Limit to avoid widget size constraints
            "region": boto3.session.Session().region_name,
            "title": "Top 10 Functions by Duration (p90)",
            "period": METRICS_PERIOD
        }
    })
    
    # Top 10 functions by error rate
    widgets.append({
        "type": "metric",
        "width": 12,
        "height": 8,
        "properties": {
            "view": "timeSeries",
            "stacked": False,
            "metrics": [
                [ { "expression": "SORT(METRICS(), MAX, 10)", "label": "Top 10 by Error Rate", "id": "e2" } ]
            ] + [["AWS/Lambda", "Errors", "FunctionName", function["FunctionName"], { "stat": "Sum", "visible": False }] 
                for function in functions[:50]],
            "region": boto3.session.Session().region_name,
            "title": "Top 10 Functions by Error Count",
            "period": METRICS_PERIOD
        }
    })
    
    # Add markdown header
    widgets.insert(0, {
        "type": "text",
        "width": 24,
        "height": 1,
        "properties": {
            "markdown": "# Lambda Performance Monitoring Dashboard\n**Summary Metrics**"
        }
    })
    
    return widgets

def create_service_section_widgets(service_name, functions):
    """
    Create widgets for a service section with its Lambda functions.
    """
    widgets = []
    
    # Add markdown header for the service
    widgets.append({
        "type": "text",
        "width": 24,
        "height": 1,
        "properties": {
            "markdown": f"## {service_name.upper()} Service Functions ({len(functions)})"
        }
    })
    
    # Create function metrics in rows
    for i in range(0, len(functions), FUNCTIONS_PER_ROW):
        row_functions = functions[i:i+FUNCTIONS_PER_ROW]
        metrics_width = DASHBOARD_WIDTH // len(row_functions)
        
        for function in row_functions:
            function_name = function['FunctionName']
            
            # Invocation count and errors
            widgets.append({
                "type": "metric",
                "width": metrics_width,
                "height": 6,
                "properties": {
                    "view": "timeSeries",
                    "stacked": False,
                    "metrics": [
                        [ "AWS/Lambda", "Invocations", "FunctionName", function_name, { "stat": "Sum", "label": "Invocations" } ],
                        [ "AWS/Lambda", "Errors", "FunctionName", function_name, { "stat": "Sum", "label": "Errors" } ],
                        [ "AWS/Lambda", "Throttles", "FunctionName", function_name, { "stat": "Sum", "label": "Throttles" } ]
                    ],
                    "region": boto3.session.Session().region_name,
                    "title": f"{function_name} - Invocations & Errors",
                    "period": METRICS_PERIOD
                }
            })
            
            # Duration metrics
            widgets.append({
                "type": "metric",
                "width": metrics_width,
                "height": 6,
                "properties": {
                    "view": "timeSeries",
                    "stacked": False,
                    "metrics": [
                        [ "AWS/Lambda", "Duration", "FunctionName", function_name, { "stat": "p50", "label": "p50" } ],
                        [ "AWS/Lambda", "Duration", "FunctionName", function_name, { "stat": "p90", "label": "p90" } ],
                        [ "AWS/Lambda", "Duration", "FunctionName", function_name, { "stat": "p99", "label": "p99" } ]
                    ],
                    "region": boto3.session.Session().region_name,
                    "title": f"{function_name} - Duration",
                    "period": METRICS_PERIOD
                }
            })
            
            # Memory utilization
            widgets.append({
                "type": "metric",
                "width": metrics_width,
                "height": 6,
                "properties": {
                    "view": "timeSeries",
                    "stacked": False,
                    "metrics": [
                        [ "AWS/Lambda", "ConcurrentExecutions", "FunctionName", function_name, { "stat": "Maximum", "label": "Concurrent Executions" } ]
                    ],
                    "region": boto3.session.Session().region_name,
                    "title": f"{function_name} - Concurrency",
                    "period": METRICS_PERIOD
                }
            })
    
    return widgets

def create_dashboard(functions):
    """
    Create the CloudWatch dashboard with all Lambda function metrics.
    """
    # Group functions by service
    service_groups = group_functions_by_service(functions)
    logger.info(f"Grouped functions into {len(service_groups)} services")
    
    # Create dashboard widgets
    dashboard_widgets = []
    
    # Add summary section
    dashboard_widgets.extend(create_summary_widgets(functions))
    
    # Add service sections
    for service_name, service_functions in service_groups.items():
        dashboard_widgets.extend(create_service_section_widgets(service_name, service_functions))
    
    # Prepare dashboard body
    dashboard_body = {
        "widgets": dashboard_widgets
    }
    
    # Convert to JSON
    dashboard_json = json.dumps(dashboard_body)
    
    # Check dashboard size limits (CloudWatch has a 500KB limit)
    dashboard_size_kb = len(dashboard_json) / 1024
    logger.info(f"Dashboard size: {dashboard_size_kb:.2f} KB")
    
    if dashboard_size_kb > 495:  # Leave some buffer
        logger.warning("Dashboard approaching size limit. Reducing number of widgets.")
        # Simplify by limiting functions per service
        MAX_FUNCS_PER_SERVICE = 10
        dashboard_widgets = []
        dashboard_widgets.extend(create_summary_widgets(functions))
        
        for service_name, service_functions in service_groups.items():
            limited_functions = service_functions[:MAX_FUNCS_PER_SERVICE]
            dashboard_widgets.extend(create_service_section_widgets(
                f"{service_name} (showing {len(limited_functions)} of {len(service_functions)})",
                limited_functions
            ))
        
        dashboard_body = {"widgets": dashboard_widgets}
        dashboard_json = json.dumps(dashboard_body)
        dashboard_size_kb = len(dashboard_json) / 1024
        logger.info(f"Reduced dashboard size: {dashboard_size_kb:.2f} KB")
    
    # Create or update the dashboard
    try:
        response = with_retries(
            cloudwatch_client.put_dashboard,
            DashboardName=DASHBOARD_NAME,
            DashboardBody=dashboard_json
        )
        logger.info(f"Successfully created/updated dashboard '{DASHBOARD_NAME}'")
        return True
    except ClientError as e:
        logger.error(f"Error creating CloudWatch dashboard: {e}")
        return False

def delete_dashboard():
    """
    Delete the Lambda Performance Monitoring Dashboard.
    """
    try:
        response = with_retries(
            cloudwatch_client.delete_dashboards,
            DashboardNames=[DASHBOARD_NAME]
        )
        logger.info(f"Successfully deleted dashboard '{DASHBOARD_NAME}'")
        return True
    except ClientError as e:
        logger.error(f"Error deleting CloudWatch dashboard: {e}")
        return False

def main():
    """
    Main function to create, update or delete the Lambda dashboard based on user input.
    """
    print("\nLambda Performance Monitoring Dashboard Tool")
    print("===========================================")
    
    # Check if dashboard exists
    try:
        response = with_retries(
            cloudwatch_client.get_dashboard,
            DashboardName=DASHBOARD_NAME
        )
        dashboard_exists = True
        print(f"Dashboard '{DASHBOARD_NAME}' already exists.")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFound':
            dashboard_exists = False
            print(f"Dashboard '{DASHBOARD_NAME}' does not exist.")
        else:
            logger.error(f"Error checking dashboard existence: {e}")
            return
    
    # Ask for user confirmation
    action = input("\nWhat would you like to do?\n"
                  "1. Create/Update dashboard\n"
                  "2. Delete dashboard\n"
                  "3. Exit\n"
                  "Enter your choice (1-3): ")
    
    if action == '1':
        confirm = input("Are you sure you want to create/update the Lambda Performance Dashboard? (yes/no): ").lower()
        if confirm == 'yes':
            logger.info("Starting Lambda Performance Monitoring Dashboard creation")
            
            try:
                # Get all Lambda functions
                functions = get_all_lambda_functions()
                logger.info(f"Retrieved {len(functions)} Lambda functions")
                
                # Create/update dashboard
                success = create_dashboard(functions)
                
                if success:
                    print(f"\n✅ Dashboard creation completed!")
                    print(f"View dashboard at: https://{boto3.session.Session().region_name}.console.aws.amazon.com/cloudwatch/home#dashboards:name={DASHBOARD_NAME}")
                else:
                    print("\n❌ Dashboard creation failed. Check logs for details.")
            
            except Exception as e:
                logger.error(f"Unexpected error: {e}", exc_info=True)
                print("\n❌ An error occurred. Check logs for details.")
        else:
            print("Operation cancelled.")
    
    elif action == '2':
        if not dashboard_exists:
            print(f"Dashboard '{DASHBOARD_NAME}' does not exist, nothing to delete.")
            return
            
        confirm = input("Are you sure you want to DELETE the Lambda Performance Dashboard? (yes/no): ").lower()
        if confirm == 'yes':
            success = delete_dashboard()
            if success:
                print(f"\n✅ Dashboard '{DASHBOARD_NAME}' has been deleted.")
            else:
                print("\n❌ Dashboard deletion failed. Check logs for details.")
        else:
            print("Operation cancelled.")
    
    elif action == '3':
        print("Exiting without changes.")
    
    else:
        print("Invalid option. Exiting without changes.")

if __name__ == "__main__":
    main()