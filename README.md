# whoAmI - Azure Function App

## Setup Instructions

### Prerequisites
- Python 3.9 or later
- Azure Functions Core Tools
- An Azure subscription with access to Azure Data Explorer (Kusto)

### Local Development Setup

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd whoAmI
   ```

2. **Set up local configuration**
   ```bash
   cd src
   cp local.settings.template.json local.settings.json
   ```

3. **Update your local configuration**
   Edit `src/local.settings.json` and replace the placeholder values:
   - `YOUR_AZURE_STORAGE_CONNECTION_STRING_OR_UseDevelopmentStorage=true`: Use `UseDevelopmentStorage=true` for local development with Azurite, or provide your Azure Storage connection string
   - `YOUR_KUSTO_CLUSTER_URL`: Your Azure Data Explorer cluster URL (e.g., `https://yourcluster.region.kusto.windows.net/`)
   - `YOUR_KUSTO_DATABASE_NAME`: The name of your Kusto database

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **Run locally**
   ```bash
   func start
   ```

### Configuration

The `local.settings.json` file contains sensitive configuration data and is excluded from version control. Always use the template file as a starting point for new environments.

### Deployment

[Add your deployment instructions here]