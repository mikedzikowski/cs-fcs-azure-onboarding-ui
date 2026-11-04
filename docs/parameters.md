# CrowdStrike Falcon Cloud Security - Parameter Reference

This document provides a comprehensive reference for all parameters used in the CrowdStrike Falcon Cloud Security Azure deployment templates.

## Parameter Categories

### 🔵 User-Supplied Parameters
Parameters that customers must provide or configure in the portal UI.

### 🟠 CrowdStrike-Supplied Parameters  
Parameters provided by CrowdStrike during onboarding or available in documentation.

### 🟣 Derived/Computed Parameters
Parameters calculated automatically from user inputs - never ask users for these.

### 🟢 Feature Flags
Boolean parameters that control conditional UI visibility and functionality.

### 🔴 Secrets
Sensitive parameters that require secure input methods.

---

## Complete Parameter Reference

| Parameter | Type | Category | Scope | Required | Default | Description |
|-----------|------|----------|-------|----------|---------|-------------|
| **subscriptionIds** | array | 🔵 User | sub/mg | ❌ | `[]` | List of Azure subscription IDs to monitor |
| **managementGroupIds** | array | 🔵 User | mg | ❌ | `[]` | List of Azure management group IDs to monitor |
| **csInfraSubscriptionId** | string | 🔵 User | sub/mg | ✅ | - | Subscription hosting CrowdStrike infrastructure |
| **azurePrincipalId** | string | 🟠 CrowdStrike | sub/mg | ✅ | - | CrowdStrike Entra ID service principal Object ID |
| **location** | string | 🔵 User | sub/mg | ❌ | deployment().location | Azure region for global resources |
| **falconApiFqdn** | string | 🟠 CrowdStrike | sub/mg | ❌ | `''` | Falcon API endpoint (region-specific) |
| **falconClientId** | string | 🟠 CrowdStrike | sub/mg | ❌* | `''` | Falcon API client ID |
| **falconClientSecret** | string | 🔴 Secret | sub/mg | ❌* | `''` | Falcon API client secret |
| **falconIpAddresses** | array | 🟠 CrowdStrike | sub/mg | ❌ | `[]` | CrowdStrike service IP addresses |
| **accountType** | string | 🟠 CrowdStrike | sub/mg | ❌ | `''` | Azure cloud environment (commercial/gov) |
| **isInitialRegistration** | bool | 🔵 User | sub/mg | ❌ | `true` | First-time vs update deployment |
| **env** | string | 🔵 User | sub/mg | ❌ | `'prod'` | Environment label (max 4 chars) |
| **tags** | object | 🔵 User | sub/mg | ❌ | CSTagVendor: 'CrowdStrike' | Resource tags |
| **resourceNamePrefix** | string | 🔵 User | sub/mg | ❌ | `''` | Resource name prefix (max 10 chars) |
| **resourceNameSuffix** | string | 🔵 User | sub/mg | ❌ | `''` | Resource name suffix (max 10 chars) |
| **enableRealTimeVisibility** | bool | 🟢 Feature | sub/mg | ❌ | `false` | Enable log ingestion and real-time detection |
| **logIngestionSettings** | object | 🔵 User | sub/mg | ❌ | Complex default | Activity Log and Entra ID log configuration |
| **enableDspm** | bool | 🟢 Feature | sub/mg | ❌ | `false` | Enable Data Security Posture Management |
| **enableVulnerabilityScanning** | bool | 🟢 Feature | sub/mg | ❌ | `false` | Enable vulnerability scanning |
| **agentlessScanningLocations** | array | 🔵 User | sub/mg | ❌** | `[]` | Azure regions for scanning deployment |
| **agentlessScanningLocationsPerSubscription** | object | 🔵 User | sub/mg | ❌** | `{}` | Per-subscription region mapping |
| **agentlessScanningDeployNatGateway** | bool | 🔵 User | sub/mg | ❌ | `true` | Deploy NAT Gateway for scanning |
| **agentlessScanningHostSubscriptionId** | string | 🔵 User | sub/mg | ❌ | `''` | Host subscription for cross-account scanning |
| **agentlessScanningCustomVnetConfiguration** | object | 🔵 User | sub/mg | ❌ | `{}` | Custom VNet subnet configuration |

*Required when enableRealTimeVisibility OR enableDspm OR enableVulnerabilityScanning is true  
**One of agentlessScanningLocations or agentlessScanningLocationsPerSubscription required when scanning enabled

## Parameter Validation Rules

### Length Constraints
- **env**: Maximum 4 characters
- **resourceNamePrefix**: Maximum 10 characters  
- **resourceNameSuffix**: Maximum 10 characters
- **Combined prefix + suffix**: Maximum 10 characters total

### Format Validation
- **azurePrincipalId**: Valid GUID format (8-4-4-4-12)
- **falconClientId**: 32-character hexadecimal string when provided
- **Resource name components**: Letters, numbers, hyphens, underscores only

### Conditional Requirements
- **Falcon API credentials**: Required when any real-time or scanning features enabled
- **Scanning locations**: Required when DSPM or vulnerability scanning enabled  
- **Host subscription**: Required when cross-account scanning enabled
- **Custom VNet subnets**: Must be in host subscription when provided

### Cross-Parameter Validation
- Custom VNet configuration requires host subscription to be specified
- Host subscription must be included in scanning location mappings
- Target subscription locations must be subset of host subscription locations
- Combined resource name length constraints apply across prefix and suffix

## Dependency Matrix

| Parameter | Triggers Visibility | Depends On |
|-----------|-------------------|------------|
| **falconClientId** | - | enableRealTimeVisibility OR enableDspm OR enableVulnerabilityScanning |
| **falconClientSecret** | - | enableRealTimeVisibility OR enableDspm OR enableVulnerabilityScanning |
| **logIngestionSettings** | Activity/Entra log options | enableRealTimeVisibility |
| **agentlessScanningLocations** | Scanning location picker | enableDspm OR enableVulnerabilityScanning |
| **agentlessScanningHostSubscriptionId** | Cross-account options | enableDspm OR enableVulnerabilityScanning |
| **agentlessScanningCustomVnetConfiguration** | Custom subnet fields | agentlessScanningHostSubscriptionId |

## Feature Flag Behavior

### enableRealTimeVisibility = true
- Shows log ingestion configuration section
- Requires falconClientId and falconClientSecret
- Enables Activity Log and Entra ID log collection options

### enableDspm = true OR enableVulnerabilityScanning = true  
- Shows scanning configuration section
- Requires falconClientId and falconClientSecret
- Requires scanning location configuration
- Enables cross-account scanning options

### Cross-account scanning enabled
- Shows host subscription selector
- Enables custom VNet configuration options
- Applies location validation between host and target subscriptions

## Default Values

### CrowdStrike Service Principal
```
azurePrincipalId: "00000000-0000-0000-0000-000000000000"  // Example - actual value provided by CrowdStrike
```

### Falcon API Endpoints by Region
```
US-1: "api.crowdstrike.com"
US-2: "api.us-2.crowdstrike.com"  
EU-1: "api.eu-1.crowdstrike.com"
US-GOV-1: "api.laggar.gcw.crowdstrike.com"
```

### CrowdStrike IP Addresses
Enter them on the Features tab when real-time visibility is on (comma-separated). They are not
stored in this repo. Get the list for your Falcon cloud (Falcon login required):

- US-1: https://docs.crowdstrike.com/access?ft:originId=ibc7ee4c
- US-2: https://docs.crowdstrike.com/access?ft:originId=a1f2fdef
- EU-1: https://docs.crowdstrike.com/access?ft:originId=yf3ab7b3

```json
["192.0.2.10", "192.0.2.11"]
```
*Example values (RFC 5737 documentation range), not CrowdStrike IPs.*

### Log Ingestion Settings Default
```json
{
  "activityLogSettings": {
    "enabled": true,
    "deployRemediationPolicy": true,
    "existingEventhub": {
      "use": false,
      "name": "",
      "namespaceName": "",
      "resourceGroupName": "",
      "subscriptionId": "",
      "consumerGroupName": ""
    }
  },
  "entraIdLogSettings": {
    "enabled": true,
    "existingEventhub": {
      "use": false,
      "name": "",
      "namespaceName": "",
      "resourceGroupName": "",
      "subscriptionId": "",
      "consumerGroupName": ""
    }
  }
}
```

## UI Mapping Examples

### Basic Deployment
```json
{
  "csInfraSubscriptionId": "subscription-guid",
  "azurePrincipalId": "principal-guid", 
  "location": "westus2",
  "enableRealTimeVisibility": false,
  "enableDspm": false,
  "enableVulnerabilityScanning": false
}
```

### Full Featured Deployment  
```json
{
  "csInfraSubscriptionId": "subscription-guid",
  "azurePrincipalId": "principal-guid",
  "location": "westus2", 
  "falconApiFqdn": "api.crowdstrike.com",
  "falconClientId": "client-id-32-chars",
  "falconClientSecret": "client-secret",
  "enableRealTimeVisibility": true,
  "enableDspm": true,
  "enableVulnerabilityScanning": true,
  "agentlessScanningLocations": ["westus2", "eastus2"],
  "agentlessScanningDeployNatGateway": true,
  "resourceNamePrefix": "cs",
  "env": "prod"
}
```

### Cross-Account Scanning
```json
{
  "agentlessScanningHostSubscriptionId": "host-subscription-guid",
  "agentlessScanningLocations": ["westus2"],
  "agentlessScanningCustomVnetConfiguration": {
    "westus2": {
      "scanners_subnet_id": "/subscriptions/{host-sub}/resourceGroups/{rg}/providers/Microsoft.Network/virtualNetworks/{vnet}/subnets/{scanners-subnet}",
      "clones_subnet_id": "/subscriptions/{host-sub}/resourceGroups/{rg}/providers/Microsoft.Network/virtualNetworks/{vnet}/subnets/{clones-subnet}"
    }
  }
}
```

---

For questions about parameter values or configuration, contact [CrowdStrike Support](https://supportportal.crowdstrike.com/).