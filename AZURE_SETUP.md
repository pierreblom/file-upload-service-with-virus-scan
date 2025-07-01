# Azure Blob Storage Setup Guide

This guide will help you set up Azure Blob Storage for the File Upload Service.

## Prerequisites

- Azure subscription
- Azure CLI installed (optional, for command-line setup)

## Option 1: Azure Portal Setup (Recommended for Beginners)

### 1. Create Storage Account

1. Go to [Azure Portal](https://portal.azure.com)
2. Click "Create a resource" → "Storage" → "Storage account"
3. Fill in the details:
   - **Subscription**: Your Azure subscription
   - **Resource group**: Create new or use existing
   - **Storage account name**: Choose a unique name (e.g., `myfileuploadservice`)
   - **Region**: Choose closest to your users
   - **Performance**: Standard (sufficient for most use cases)
   - **Redundancy**: LRS for development, GRS for production

4. Click "Review + create" → "Create"

### 2. Get Connection String

1. Go to your storage account
2. Navigate to "Security + networking" → "Access keys"
3. Copy the "Connection string" under key1 or key2
4. This will be your `AZURE_STORAGE_CONNECTION_STRING`

### 3. Create Container (Optional)

The application will create the container automatically, but you can create it manually:

1. In your storage account, go to "Data storage" → "Containers"
2. Click "+ Container"
3. Name: `file-upload-service` (or match your `AZURE_CONTAINER_NAME`)
4. Public access level: Private (recommended)

## Option 2: Azure CLI Setup

### 1. Install Azure CLI

```bash
# On macOS
brew install azure-cli

# On Ubuntu/Debian
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# On Windows
# Download from: https://aka.ms/installazurecliwindows
```

### 2. Login to Azure

```bash
az login
```

### 3. Create Resource Group

```bash
az group create \
  --name file-upload-rg \
  --location eastus
```

### 4. Create Storage Account

```bash
az storage account create \
  --name myfileuploadservice \
  --resource-group file-upload-rg \
  --location eastus \
  --sku Standard_LRS \
  --kind StorageV2
```

### 5. Get Connection String

```bash
az storage account show-connection-string \
  --name myfileuploadservice \
  --resource-group file-upload-rg \
  --output tsv
```

### 6. Create Container

```bash
az storage container create \
  --name file-upload-service \
  --connection-string "your-connection-string-here"
```

## Configuration

### Environment Variables

Add these to your `.env` file:

```bash
# Storage Configuration
STORAGE_TYPE=azure

# Azure Blob Storage Configuration
AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;AccountName=myfileuploadservice;AccountKey=your-key-here;EndpointSuffix=core.windows.net
AZURE_CONTAINER_NAME=file-upload-service
```

### Alternative Configuration (Account Name + Key)

Instead of connection string, you can use:

```bash
AZURE_STORAGE_ACCOUNT_NAME=myfileuploadservice
AZURE_STORAGE_ACCOUNT_KEY=your-account-key-here
AZURE_CONTAINER_NAME=file-upload-service
```

## Testing the Setup

### 1. Test Connection

```bash
# Install Azure CLI if not already installed
pip install azure-storage-blob

# Test Python connection
python3 -c "
from azure.storage.blob import BlobServiceClient
conn_str = 'your-connection-string-here'
client = BlobServiceClient.from_connection_string(conn_str)
print('✅ Connection successful!')
for container in client.list_containers():
    print(f'Container: {container.name}')
"
```

### 2. Start the Service with Azure

```bash
# Using Docker Compose with Azure override
docker-compose -f docker-compose.yml -f docker-compose.azure.yml up -d

# Or set environment variables and use regular docker-compose
export STORAGE_TYPE=azure
export AZURE_STORAGE_CONNECTION_STRING="your-connection-string"
docker-compose up -d
```

### 3. Test File Upload

```bash
# Test the API
python test_api.py
```

## Security Best Practices

### 1. Access Keys Management

- **Rotate keys regularly** (Azure recommends every 90 days)
- **Use Azure Key Vault** for production environments
- **Enable soft delete** for blob recovery

```bash
# Enable soft delete
az storage account blob-service-properties update \
  --account-name myfileuploadservice \
  --enable-delete-retention true \
  --delete-retention-days 30
```

### 2. Network Security

```bash
# Restrict access to specific IPs (optional)
az storage account network-rule add \
  --account-name myfileuploadservice \
  --ip-address your-server-ip
```

### 3. Enable Logging

```bash
# Enable diagnostic logs
az storage logging update \
  --account-name myfileuploadservice \
  --account-key your-account-key \
  --services b \
  --log rwd \
  --retention 30
```

## Cost Optimization

### 1. Choose Right Storage Tier

- **Hot**: Frequently accessed files
- **Cool**: Infrequently accessed files (lower storage cost)
- **Archive**: Rarely accessed files (lowest cost)

```bash
# Set default access tier to Cool for cost savings
az storage account update \
  --name myfileuploadservice \
  --resource-group file-upload-rg \
  --access-tier Cool
```

### 2. Lifecycle Management

Create lifecycle policies to automatically move old files to cheaper tiers:

```json
{
  "rules": [
    {
      "name": "MoveToArchive",
      "type": "Lifecycle",
      "definition": {
        "filters": {
          "blobTypes": ["blockBlob"],
          "prefixMatch": ["uploads/"]
        },
        "actions": {
          "baseBlob": {
            "tierToCool": {
              "daysAfterModificationGreaterThan": 30
            },
            "tierToArchive": {
              "daysAfterModificationGreaterThan": 90
            },
            "delete": {
              "daysAfterModificationGreaterThan": 365
            }
          }
        }
      }
    }
  ]
}
```

## Monitoring

### 1. Azure Monitor

Set up alerts for:
- Storage usage
- Request failures
- High latency

### 2. Application Insights

Integrate with Application Insights for detailed monitoring:

```bash
az extension add --name application-insights
az monitor app-insights component create \
  --app file-upload-insights \
  --location eastus \
  --resource-group file-upload-rg
```

## Troubleshooting

### Common Issues

1. **Connection String Format**
   ```
   Ensure it starts with: DefaultEndpointsProtocol=https;AccountName=...
   ```

2. **Container Not Found**
   ```bash
   # Check if container exists
   az storage container exists \
     --name file-upload-service \
     --connection-string "your-connection-string"
   ```

3. **Access Denied**
   ```bash
   # Verify access key is correct
   az storage account keys list \
     --account-name myfileuploadservice \
     --resource-group file-upload-rg
   ```

### Debug Mode

Enable debug logging in your application:

```bash
export DEBUG=true
export AZURE_STORAGE_LOG_LEVEL=DEBUG
docker-compose up
```

## Production Considerations

1. **Use Managed Identity** instead of connection strings
2. **Enable geo-redundancy** (GRS/RA-GRS)
3. **Set up cross-region replication**
4. **Monitor costs** with Azure Cost Management
5. **Use Azure CDN** for faster downloads

## Support

For Azure-specific issues:
- [Azure Storage Documentation](https://docs.microsoft.com/en-us/azure/storage/)
- [Azure Support](https://azure.microsoft.com/en-us/support/)
- [Azure Storage Python SDK](https://github.com/Azure/azure-sdk-for-python/tree/main/sdk/storage/azure-storage-blob) 