import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from azure.kusto.data.exceptions import KustoServiceError

# Initialize the Function App
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Constants for common parameters
_TIME_RANGE_PROPERTY_NAME = "timeRange"
_SUBSCRIPTION_ID_PROPERTY_NAME = "subscriptionId"
_LIMIT_PROPERTY_NAME = "limit"
DEFAULT_RESULT_LIMIT = 100

# Define a class to represent tool properties
class ToolProperty:
    """Represents a tool property with name, type, and description."""
    
    def __init__(self, property_name: str, property_type: str, description: str) -> None:
        self.property_name = property_name
        self.property_type = property_type
        self.description = description

    def to_dict(self) -> Dict[str, str]:
        """Convert the tool property to a dictionary representation."""
        return {
            "propertyName": self.property_name,
            "propertyType": self.property_type,
            "description": self.description,
        }

# Helper function to parse time range and convert to Kusto datetime
def parse_time_range(time_range: str) -> str:
    """
    Parse time range parameter and return a Kusto-compatible datetime string.
    
    Args:
        time_range: Time range in format like "7d", "24h", "30m" or default to "7d"
    
    Returns:
        Kusto datetime string for the start time
    """
    if not time_range:
        time_range = "7d"  # Default to 7 days
    
    # Parse the time range
    unit = time_range[-1].lower()
    try:
        value = int(time_range[:-1])
    except ValueError:
        # Default to 7 days if parsing fails
        value = 7
        unit = 'd'
    
    # Calculate start time
    now = datetime.utcnow()
    if unit == 'd':
        start_time = now - timedelta(days=value)
    elif unit == 'h':
        start_time = now - timedelta(hours=value)
    elif unit == 'm':
        start_time = now - timedelta(minutes=value)
    else:
        # Default to days
        start_time = now - timedelta(days=value)
    
    return start_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")

# Helper function to generate Kusto queries
def generate_function_apps_query(start_time: str, subscription_id: str, limit: int = DEFAULT_RESULT_LIMIT) -> str:
    """
    Generate a Kusto query to find recent active Function Apps.
    
    Args:
        start_time: Start time in Kusto datetime format
        subscription_id: Required subscription ID filter
        limit: Maximum number of results to return (default: 100)
    
    Returns:
        Kusto query string
    """
    # Build the query with proper escaping and formatting
    query_lines = [
        "WawsAn_omgsiteentity",
        f"| where pdate >= datetime('{start_time}')",
        "| where IsFunction == 1",
        "| where IsActive == 1", 
        f"| where Subscription == '{subscription_id}'",
        "| distinct SiteName",
        f"| take {limit}"
    ]
    
    return "\n".join(query_lines)

# Helper function to get Kusto access token
def get_kusto_access_token() -> str:
    """
    Get an access token for Azure Data Explorer (Kusto).
    Uses DefaultAzureCredential for local development and EasyAuth headers for Azure deployment.
    
    Returns:
        Access token string for Kusto authentication
    """
    # Check if running in Azure (EasyAuth headers present)
    if os.getenv("HTTP_X_MS_TOKEN_AAD_ACCESS_TOKEN"):
        # Use EasyAuth token when deployed to Azure
        access_token = os.getenv("HTTP_X_MS_TOKEN_AAD_ACCESS_TOKEN")
        logging.info("Using EasyAuth authentication for Kusto")
        return access_token
    else:
        # Use DefaultAzureCredential for local development
        credential = DefaultAzureCredential()
        logging.info("Using DefaultAzureCredential for Kusto local development")
        token = credential.get_token("https://help.kusto.windows.net/.default")
        return token.token

# Define the tool properties for Function Apps monitoring
tool_properties_function_apps_object: List[ToolProperty] = [
    ToolProperty(_TIME_RANGE_PROPERTY_NAME, "string", "Time range to search as a string with number followed by unit: 'd' for days, 'h' for hours, 'm' for minutes. Examples: '7d' (7 days), '24h' (24 hours), '30m' (30 minutes). If not provided, defaults to '7d'."),
    ToolProperty(_SUBSCRIPTION_ID_PROPERTY_NAME, "string", "Azure subscription ID as a GUID string (e.g., '12345678-1234-1234-1234-123456789abc'). This parameter is required to scope the search to a specific Azure subscription."),
    ToolProperty(_LIMIT_PROPERTY_NAME, "integer", "Maximum number of Function Apps to return. If not provided, defaults to 100.")
]

# Convert the tool properties to JSON
tool_properties_function_apps_json: str = json.dumps([prop.to_dict() for prop in tool_properties_function_apps_object])


# Helper function to execute Kusto queries
def execute_kusto_query(query: str) -> str:
    """
    Execute a Kusto query and return results as JSON.
    
    Args:
        query: The Kusto query to execute
    
    Returns:
        JSON string with query results or error message
    """
    try:
        logging.info(f"Executing Kusto query: {query[:100]}...")  # Log first 100 chars for debugging
        
        # Get environment variables for Kusto configuration
        cluster_url = os.getenv("KUSTO_CLUSTER_URL")
        database_name = os.getenv("KUSTO_DATABASE_NAME")
        
        if not cluster_url:
            return "Error: KUSTO_CLUSTER_URL environment variable is not set"
        
        if not database_name:
            return "Error: KUSTO_DATABASE_NAME environment variable is not set"
        
        # Get access token for Kusto
        access_token = get_kusto_access_token()
        
        # Create Kusto connection
        kcsb = KustoConnectionStringBuilder.with_aad_application_token_authentication(
            cluster_url, access_token
        )
        
        # Create Kusto client
        client = KustoClient(kcsb)
        
        # Execute the query
        response = client.execute_query(database_name, query)
        
        # Process the results
        results = []
        for row in response.primary_results[0]:
            # Convert each row to a dictionary
            row_dict = {}
            for i, column in enumerate(response.primary_results[0].columns):
                row_dict[column.column_name] = row[i]
            results.append(row_dict)
        
        # Return results as JSON
        result_json = json.dumps(results, indent=2, default=str)
        logging.info(f"Successfully executed Kusto query, returned {len(results)} rows")
        return result_json
                
    except KustoServiceError as e:
        error_msg = f"Kusto service error: {str(e)}"
        logging.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Error executing Kusto query: {str(e)}"
        logging.error(error_msg)
        return error_msg


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="getRecentActiveFunctionApps",
    description="Get Function Apps that have been active recently with their activity details.",
    toolProperties=tool_properties_function_apps_json,
)
def get_recent_active_function_apps(context: str) -> str:
    """
    Get Function Apps that have been active recently.

    Args:
        context: The trigger context containing time range and required subscription ID.

    Returns:
        str: JSON with active Function Apps or an error message.
    """
    try:
        # Parse the context to get arguments
        content = json.loads(context)
        arguments = content.get("arguments", {})
        
        time_range = arguments.get(_TIME_RANGE_PROPERTY_NAME, "7d")
        subscription_id = arguments.get(_SUBSCRIPTION_ID_PROPERTY_NAME)
        limit = arguments.get(_LIMIT_PROPERTY_NAME, DEFAULT_RESULT_LIMIT)
        
        # Validate required parameters
        if not subscription_id:
            return "Error: subscriptionId parameter is required"
        
        # Validate and convert limit to integer
        try:
            limit = int(limit)
            if limit <= 0:
                limit = DEFAULT_RESULT_LIMIT
        except (ValueError, TypeError):
            limit = DEFAULT_RESULT_LIMIT
        
        # Generate the start time
        start_time = parse_time_range(time_range)
        
        # Generate and execute the query
        query = generate_function_apps_query(start_time, subscription_id, limit)
        return execute_kusto_query(query)
                
    except json.JSONDecodeError as e:
        error_msg = f"Error parsing JSON context: {str(e)}"
        logging.error(error_msg)
        return error_msg
    except Exception as e:
        error_msg = f"Error getting active Function Apps: {str(e)}"
        logging.error(error_msg)
        return error_msg