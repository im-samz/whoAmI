import base64
import json
import logging
import os
import urllib.parse

import azure.functions as func
from azure.identity import DefaultAzureCredential
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from azure.kusto.data.exceptions import KustoServiceError
import requests

# Initialize the Function App
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Constants for the whoAmI function
_INCLUDE_EMAIL_PROPERTY_NAME = "includeEmail"

# Constants for the Kusto query function
_QUERY_PROPERTY_NAME = "query"

# Define a class to represent tool properties
class ToolProperty:
    def __init__(self, property_name: str, property_type: str, description: str):
        self.propertyName = property_name
        self.propertyType = property_type
        self.description = description

    def to_dict(self):
        return {
            "propertyName": self.propertyName,
            "propertyType": self.propertyType,
            "description": self.description,
        }

# Helper function to get access token
def get_access_token():
    """
    Get an access token for Microsoft Graph.
    Uses DefaultAzureCredential for local development and EasyAuth headers for Azure deployment.
    """
    # Check if running in Azure (EasyAuth headers present)
    if os.getenv("HTTP_X_MS_TOKEN_AAD_ACCESS_TOKEN"):
        # Use EasyAuth token when deployed to Azure
        access_token = os.getenv("HTTP_X_MS_TOKEN_AAD_ACCESS_TOKEN")
        logging.info("Using EasyAuth authentication")
        return access_token
    else:
        # Use DefaultAzureCredential for local development
        credential = DefaultAzureCredential()
        logging.info("Using DefaultAzureCredential for local development")
        token = credential.get_token("https://graph.microsoft.com/.default")
        return token.token


# Helper function to format user information
def format_user_info(display_name: str, email: str = None, include_email: bool = False) -> str:
    """
    Format user information based on the include_email parameter.
    
    Args:
        display_name: The user's display name
        email: The user's email address (optional)
        include_email: Whether to include email in the result
    
    Returns:
        Formatted user information string
    """
    if include_email and email:
        return f"{display_name} ({email})"
    return display_name

# Helper function to get Kusto access token
def get_kusto_access_token():
    """
    Get an access token for Azure Data Explorer (Kusto).
    Uses DefaultAzureCredential for local development and EasyAuth headers for Azure deployment.
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

# Helper function to decode the query parameter
def decode_query(encoded_query: str) -> str:
    """
    Decode the URL-encoded query parameter.
    
    Args:
        encoded_query: The URL-encoded query string
    
    Returns:
        Decoded query string
    """
    try:
        return urllib.parse.unquote(encoded_query)
    except Exception as e:
        logging.error(f"Failed to decode query: {str(e)}")
        return encoded_query  # Return as-is if decoding fails

# Define the tool properties using the ToolProperty class
tool_properties_who_am_i_object = [
    ToolProperty(_INCLUDE_EMAIL_PROPERTY_NAME, "boolean", "Whether to include email address in the response.")
]

# Convert the tool properties to JSON
tool_properties_who_am_i_json = json.dumps([prop.to_dict() for prop in tool_properties_who_am_i_object])

# Define the tool properties for the Kusto query function
tool_properties_kusto_query_object = [
    ToolProperty(_QUERY_PROPERTY_NAME, "string", "The encoded Kusto query to execute against the database.")
]

# Convert the tool properties to JSON
tool_properties_kusto_query_json = json.dumps([prop.to_dict() for prop in tool_properties_kusto_query_object])


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="whoAmI",
    description="Determine who I am by searching Microsoft Graph.",
    toolProperties=tool_properties_who_am_i_json,
)
def who_am_i(context) -> str:
    """
    Determines who the current user is by querying Microsoft Graph.
    Uses DefaultAzureCredential for local development and EasyAuth for Azure deployment.

    Args:
        context: The trigger context containing the input arguments.

    Returns:
        str: The display name of the current user (optionally with email) or an error message.
    """
    try:
        # Parse the context to get arguments
        content = json.loads(context)
        include_email = content.get("arguments", {}).get(_INCLUDE_EMAIL_PROPERTY_NAME, False)
        
        # Check if running in Azure (EasyAuth headers present)
        if os.getenv("HTTP_X_MS_TOKEN_AAD_ACCESS_TOKEN"):
            # For Azure deployment with EasyAuth
            user_principal = os.getenv("HTTP_X_MS_CLIENT_PRINCIPAL")
            if not user_principal:
                return "No user principal found in EasyAuth headers"
                
            decoded_principal = base64.b64decode(user_principal).decode('utf-8')
            principal_data = json.loads(decoded_principal)
            display_name = principal_data.get("name", "Unknown User")
            email = principal_data.get("email")
            
            result = format_user_info(display_name, email, include_email)
            logging.info(f"Successfully retrieved user info from EasyAuth: {result}")
            return result
        else:
            # For local development with DefaultAzureCredential
            access_token = get_access_token()
            
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            response = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers)
            
            if response.status_code != 200:
                return f"Failed to get user info: {response.status_code} - {response.text}"
                
            user_info = response.json()
            display_name = user_info.get("displayName", "Unknown User")
            email = user_info.get("mail") or user_info.get("userPrincipalName")
            
            result = format_user_info(display_name, email, include_email)
            logging.info(f"Successfully retrieved user info: {result}")
            return result
                
    except Exception as e:
        error_msg = f"Error determining user identity: {str(e)}"
        logging.error(error_msg)
        return error_msg


@app.generic_trigger(
    arg_name="context",
    type="mcpToolTrigger",
    toolName="kustoQuery",
    description="Execute a query against a Kusto database and return the results.",
    toolProperties=tool_properties_kusto_query_json,
)
def kusto_query(context) -> str:
    """
    Executes a query against a Kusto database.
    Uses DefaultAzureCredential for local development and EasyAuth for Azure deployment.

    Args:
        context: The trigger context containing the input arguments including the encoded query.

    Returns:
        str: The query results as JSON or an error message.
    """
    try:
        # Parse the context to get arguments
        content = json.loads(context)
        encoded_query = content.get("arguments", {}).get(_QUERY_PROPERTY_NAME)
        
        if not encoded_query:
            return "Error: No query provided in the request"
        
        # Decode the query
        query = decode_query(encoded_query)
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
