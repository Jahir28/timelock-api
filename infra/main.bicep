targetScope = 'resourceGroup'

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Short lowercase prefix. Keep letters and numbers only because it is used in the ACR name.')
@minLength(3)
@maxLength(12)
param prefix string = 'timelock'

@description('SQL administrator username.')
param sqlAdminUser string = 'sqladminuser'

@secure()
@description('SQL administrator password.')
param sqlAdminPassword string

@description('Container repository name inside Azure Container Registry.')
param dockerImageName string = 'timelock-api'

@description('Container image tag used by App Service.')
param dockerImageTag string = 'latest'

var uniqueSuffix = uniqueString(resourceGroup().id, prefix)
var namePrefix = toLower('${prefix}${uniqueSuffix}')
var acrName = '${namePrefix}acr'
var sqlServerName = '${namePrefix}-sql'
var databaseName = 'timelockdb'
var planName = '${namePrefix}-plan'
var appName = '${namePrefix}-api'
var imageReference = '${acr.properties.loginServer}/${dockerImageName}:${dockerImageTag}'
var appUrl = 'https://${appName}.azurewebsites.net'

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: sqlServerName
  location: location
  properties: {
    administratorLogin: sqlAdminUser
    administratorLoginPassword: sqlAdminPassword
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Enabled'
  }
}

resource sqlDb 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  name: databaseName
  parent: sqlServer
  location: location
  sku: {
    name: 'Basic'
    tier: 'Basic'
  }
}

resource allowAzureServices 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
  name: 'AllowAzureServices'
  parent: sqlServer
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
}

resource app 'Microsoft.Web/sites@2023-12-01' = {
  name: appName
  location: location
  kind: 'app,linux,container'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'DOCKER|${imageReference}'
      acrUseManagedIdentityCreds: true
      alwaysOn: true
      appSettings: [
        {
          name: 'DB_SERVER'
          value: sqlServer.properties.fullyQualifiedDomainName
        }
        {
          name: 'DB_NAME'
          value: sqlDb.name
        }
        {
          name: 'DB_USER'
          value: sqlAdminUser
        }
        {
          name: 'DB_PASSWORD'
          value: sqlAdminPassword
        }
        {
          name: 'PUBLIC_BASE_URL'
          value: appUrl
        }
        {
          name: 'WEBSITES_PORT'
          value: '8000'
        }
      ]
    }
  }
}

resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, app.id, 'AcrPull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output acrName string = acr.name
output acrLoginServer string = acr.properties.loginServer
output appName string = app.name
output appUrl string = appUrl
output imageReference string = imageReference
output sqlServerName string = sqlServer.name
output databaseName string = sqlDb.name
