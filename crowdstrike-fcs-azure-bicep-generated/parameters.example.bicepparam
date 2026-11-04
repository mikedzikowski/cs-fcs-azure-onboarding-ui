// Example parameters - copy to parameters.bicepparam (git-ignored) and fill in your values.
// The CrowdStrike console generates a populated version of this file during registration.
using './cs-deployment-management-group.bicep'

// Required: Client ID for the Falcon API.
param falconClientId = '<falcon-api-client-id>'
// Required: Client Secret for the Falcon API. Read from the environment, never stored here:
//   export FALCON_CLIENT_SECRET='<secret>'
param falconClientSecret = readEnvironmentVariable('FALCON_CLIENT_SECRET', '')

// Required: Falcon API FQDN for your CrowdStrike environment
param falconApiFqdn = 'api.crowdstrike.com'
// Required: Principal Id of Falcon Cloud Security App in Entra ID.
param azurePrincipalId = '00000000-0000-0000-0000-000000000000'
// Azure resources to monitor - You can use subscriptions, management groups, or both
param managementGroupIds = []
param subscriptionIds = []
// Required: Azure subscription that will host CrowdStrike infrastructure
param csInfraSubscriptionId = '00000000-0000-0000-0000-000000000000'
// Optional: CrowdStrike IP addresses for network security - see "Allow CrowdStrike IP Addresses"
// in the CrowdStrike docs for the list for your Falcon cloud.
param falconIpAddresses = []
param isInitialRegistration = true
param enableRealTimeVisibility = true
// Optional: Configure log ingestion settings
param logIngestionSettings = {}
// Optional: Configure Agentless Scanning
param enableDspm = false

param agentlessScanningDeployNatGateway = true
param agentlessScanningLocations = null

// Optional: Resource naming customization
param resourceNamePrefix = ''
param resourceNameSuffix = ''
param env = 'prod'
param tags = {
  CSTagVendor: 'CrowdStrike'
}
param location = 'westus'
