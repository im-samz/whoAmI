import base64
import json
import logging
import os

import azure.functions as func
from azure.identity import DefaultAzureCredential
import requests

# Initialize the Function App
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Constants for the whoAmI function
_INCLUDE_EMAIL_PROPERTY_NAME = "includeEmail"

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

# Define the tool properties using the ToolProperty class
tool_properties_who_am_i_object = [
    ToolProperty(_INCLUDE_EMAIL_PROPERTY_NAME, "boolean", "Whether to include email address in the response.")
]

# Convert the tool properties to JSON
tool_properties_who_am_i_json = json.dumps([prop.to_dict() for prop in tool_properties_who_am_i_object])


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
