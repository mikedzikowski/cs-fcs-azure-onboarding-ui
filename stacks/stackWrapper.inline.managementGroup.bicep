targetScope = 'managementGroup'

metadata name = 'CrowdStrike Falcon - Deployment Stack Wrapper (MG scope, inline, self-contained)'
metadata description = 'Creates a management-group-scoped Microsoft.Resources/deploymentStacks that deploys the CrowdStrike management-group engine template inline. Used to TEST the stack-creating UI via a Template Spec with no external hosting.'
metadata owner = 'CrowdStrike'

/*
  Management-group counterpart of stackWrapper.inline.subscription.bicep.
  The engine (dist/cs-deployment-management-group.json) is embedded inline via loadJsonContent,
  so the Template Spec is fully self-contained. Run scripts/create-templatespec-stack-mg.sh,
  which builds dist/*.json BEFORE compiling this file.

  Copyright (c) 2025 CrowdStrike, Inc.
*/

/* ---- Parameters mapped 1:1 from the MG Form (ui/uiFormDefinition.templatespec.managementGroup.json) ---- */
@description('List of Azure management group IDs to monitor.')
param managementGroupIds array = []

@description('List of Azure subscription IDs to monitor (in addition to those under the management groups).')
param subscriptionIds array = []

@description('Subscription ID where CrowdStrike infrastructure resources are deployed.')
param csInfraSubscriptionId string = ''

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

@description('Azure region for global resources (role definitions, event hub) and the stack itself.')
param location string = deployment().location

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

@description('Tags applied to deployed resources.')
param tags object = {
  CSTagVendor: 'CrowdStrike'
}

/* ---- Deployment stack configuration ---- */
@description('What happens to managed resources when they leave the stack. Test default: detach (safe). Use deleteAll for easy teardown.')
@allowed(['detachAll', 'deleteResources', 'deleteAll'])
param stackActionOnUnmanage string = 'detachAll'

@description('Resource-lock mode enforced by the stack deny-assignment.')
@allowed(['none', 'denyDelete', 'denyWriteAndDelete'])
param stackDenySettingsMode string = 'none'

/* ---- Derived ---- */
var environment = length(env) > 0 ? '-${env}' : env
var stackName = '${resourceNamePrefix}crowdstrike-falcon-mg${environment}${resourceNameSuffix}'
var excludedPrincipals = empty(azurePrincipalId) ? [] : [azurePrincipalId]

resource crowdStrikeStack 'Microsoft.Resources/deploymentStacks@2025-07-01' = {
  name: stackName
  location: location
  tags: tags
  properties: {
    description: 'CrowdStrike Falcon Cloud Security onboarding (management group scope).'
    actionOnUnmanage: {
      resources: stackActionOnUnmanage == 'detachAll' ? 'detach' : 'delete'
      resourceGroups: stackActionOnUnmanage == 'deleteAll' ? 'delete' : 'detach'
      managementGroups: stackActionOnUnmanage == 'deleteAll' ? 'delete' : 'detach'
    }
    denySettings: {
      mode: stackDenySettingsMode
      excludedPrincipals: stackDenySettingsMode == 'none' ? [] : excludedPrincipals
      applyToChildScopes: false
    }
    // MG engine embedded at build time - self-contained.
    template: loadJsonContent('../dist/cs-deployment-management-group.json')
    parameters: {
      managementGroupIds: { value: managementGroupIds }
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
    }
  }
}

output deploymentStackId string = crowdStrikeStack.id
output deploymentStackName string = stackName