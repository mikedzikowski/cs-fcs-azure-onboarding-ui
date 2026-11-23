targetScope = 'subscription'

metadata name = 'CrowdStrike Falcon - Deployment Stack Wrapper (inline, self-contained)'
metadata description = 'Creates a Microsoft.Resources/deploymentStacks that deploys the CrowdStrike subscription-scope engine template inline. Used to TEST the stack-creating UI via a Template Spec with no external hosting.'
metadata owner = 'CrowdStrike'

/*
  This wrapper exists so a portal Form (uiFormDefinition) can create a DEPLOYMENT STACK.
  The portal's Form/custom-deploy blades cannot create a stack natively, so we deploy this
  thin template whose only resource is a deploymentStack. The stack then owns and locks the
  real CrowdStrike resources (role assignments, Event Hub, Key Vault, policies, etc.).

  The engine template (dist/cs-deployment-subscription.json) is embedded INLINE via
  loadJsonContent so the Template Spec is fully self-contained - no GitHub/blob hosting needed.
  Run scripts/create-templatespec-stack.sh, which builds dist/*.json BEFORE compiling this file.

  Copyright (c) 2025 CrowdStrike, Inc.
*/

/* ---- Parameters mapped 1:1 from the Form (ui/uiFormDefinition.templatespec.json outputs) ---- */
@description('List of Azure subscription IDs to monitor.')
param subscriptionIds array = []

@description('Subscription ID where CrowdStrike infrastructure resources are deployed.')
param csInfraSubscriptionId string = ''

@description('Azure region for global resources (role definitions, event hub).')
param location string = deployment().location

@description('Principal ID of the CrowdStrike Entra ID application (service principal object ID).')
param azurePrincipalId string

@description('Base URL of the Falcon API.')
param falconApiFqdn string = ''

@description('CrowdStrike IP addresses allowed through the Event Hub firewall (per Falcon cloud).')
param falconIpAddresses array = []

@description('Client ID for the Falcon API.')
param falconClientId string = ''

@description('Client secret for the Falcon API.')
@secure()
param falconClientSecret string = ''

@description('Azure cloud type: "commercial" or "gov".')
param accountType string = ''

@description('Enable real-time visibility and detection (Activity + Entra logs).')
param enableRealTimeVisibility bool = false

@description('Enable Data Security Posture Management (DSPM).')
param enableDspm bool = false

@description('Enable vulnerability scanning.')
param enableVulnerabilityScanning bool = false

@description('Azure regions where agentless scanning is deployed.')
param agentlessScanningLocations array = []

@maxLength(10)
@description('Optional resource name prefix.')
param resourceNamePrefix string = ''

@maxLength(10)
@description('Optional resource name suffix.')
param resourceNameSuffix string = ''

@maxLength(4)
@description('Environment label (prod, stag, dev).')
param env string = 'prod'

@description('Whether this is the initial registration.')
param isInitialRegistration bool = true

@description('Tags applied to deployed resources.')
param tags object = {
  CSTagVendor: 'CrowdStrike'
}

@description('Resource ID of an existing storage account for the engine\'s deployment scripts (Azure Container Instance) instead of the auto-created one. Must be in csInfraSubscriptionId. Empty = auto-create.')
param deploymentScriptStorageAccountId string = ''

@description('Resource ID of a subnet delegated to Microsoft.ContainerInstance/containerGroups (in csInfraSubscriptionId). When set, the script mounts the storage account with its managed identity and no key is passed; when empty, the wrapper looks up the storage account key.')
param deploymentScriptSubnetId string = ''

@description('Log ingestion settings, including optional use of an existing Event Hub for Activity and/or Entra ID logs.')
param logIngestionSettings object = {
  activityLogSettings: {
    enabled: true
    deployRemediationPolicy: true
    existingEventhub: {
      use: false
      name: ''
      namespaceName: ''
      resourceGroupName: ''
      subscriptionId: ''
      consumerGroupName: ''
    }
  }
  entraIdLogSettings: {
    enabled: true
    existingEventhub: {
      use: false
      name: ''
      namespaceName: ''
      resourceGroupName: ''
      subscriptionId: ''
      consumerGroupName: ''
    }
  }
}

/* ---- Deployment stack configuration ---- */
@description('What happens to managed resources when they leave the stack. Test default: detach (safe). Use deleteAll for easy teardown.')
@allowed(['detachAll', 'deleteResources', 'deleteAll'])
param stackActionOnUnmanage string = 'detachAll'

@description('Resource-lock mode enforced by the stack deny-assignment.')
@allowed(['none', 'denyDelete', 'denyWriteAndDelete'])
param stackDenySettingsMode string = 'none'

/* ---- Derived ---- */
// Fixed name used by CrowdStrike's deprovisioning steps (az stack sub delete --name cs-subscription-stack).
var stackName = 'cs-subscription-stack'

// CrowdStrike's SP must stay unblocked so it can operate even under a deny lock.
var excludedPrincipals = empty(azurePrincipalId) ? [] : [azurePrincipalId]

// deploymentScriptSettings for the engine (CrowdStrike README: "Deployment fails because the
// auto-created deployment script storage account violates policy"). Without a subnet, Azure
// Container Instances can only mount the share with a key, so it is looked up here rather than
// typed into the form. Note: a deployment stack stores it readable in the stack's parameters.
var useScriptStorage = !empty(deploymentScriptStorageAccountId)
var scriptStorageIdParts = split(deploymentScriptStorageAccountId, '/')

// An existing reference deploys nothing; listKeys() below only runs on the no-subnet branch.
resource scriptStorage 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: useScriptStorage ? last(scriptStorageIdParts) : 'unused'
  scope: resourceGroup(useScriptStorage ? scriptStorageIdParts[2] : csInfraSubscriptionId, useScriptStorage ? scriptStorageIdParts[4] : 'unused')
}

// null (the engine's default) unless a storage account is chosen. Keep `parameters` a literal
// object: preflight doesn't run listKeys(), so an expression around the whole block fails validation.
var deploymentScriptSettings = !useScriptStorage
  ? null
  : (empty(deploymentScriptSubnetId)
      ? { storageAccountId: deploymentScriptStorageAccountId, storageAccountKey: scriptStorage.listKeys().keys[0].value }
      : { storageAccountId: deploymentScriptStorageAccountId, subnetId: deploymentScriptSubnetId })

resource crowdStrikeStack 'Microsoft.Resources/deploymentStacks@2025-07-01' = {
  name: stackName
  location: location
  tags: tags
  properties: {
    description: 'CrowdStrike Falcon Cloud Security onboarding (subscription scope).'
    actionOnUnmanage: {
      resources: stackActionOnUnmanage == 'detachAll' ? 'detach' : 'delete'
      resourceGroups: stackActionOnUnmanage == 'deleteAll' ? 'delete' : 'detach'
    }
    denySettings: {
      mode: stackDenySettingsMode
      excludedPrincipals: stackDenySettingsMode == 'none' ? [] : excludedPrincipals
      applyToChildScopes: false
    }
    // Engine template embedded at build time - self-contained, no external hosting.
    template: loadJsonContent('../dist/cs-deployment-subscription.json')
    parameters: {
      subscriptionIds: { value: subscriptionIds }
      csInfraSubscriptionId: { value: csInfraSubscriptionId }
      location: { value: location }
      azurePrincipalId: { value: azurePrincipalId }
      falconApiFqdn: { value: falconApiFqdn }
      falconIpAddresses: { value: falconIpAddresses }
      falconClientId: { value: falconClientId }
      falconClientSecret: { value: falconClientSecret }
      accountType: { value: accountType }
      enableRealTimeVisibility: { value: enableRealTimeVisibility }
      enableDspm: { value: enableDspm }
      enableVulnerabilityScanning: { value: enableVulnerabilityScanning }
      agentlessScanningLocations: { value: agentlessScanningLocations }
      resourceNamePrefix: { value: resourceNamePrefix }
      resourceNameSuffix: { value: resourceNameSuffix }
      env: { value: env }
      isInitialRegistration: { value: isInitialRegistration }
      logIngestionSettings: { value: logIngestionSettings }
      tags: { value: tags }
      deploymentScriptSettings: { value: deploymentScriptSettings }
    }
  }
}

output deploymentStackId string = crowdStrikeStack.id
output deploymentStackName string = stackName