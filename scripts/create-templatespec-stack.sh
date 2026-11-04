#!/usr/bin/env bash
#
# Publish a Template Spec whose template CREATES A DEPLOYMENT STACK, with the portal Form
# (uiFormDefinition) attached. Deploying it from the portal renders the UI and, on Create,
# provisions a Microsoft.Resources/deploymentStacks that manages all CrowdStrike resources.
#
# Fully self-contained: the engine template is embedded inline in the wrapper (loadJsonContent),
# so nothing needs to be hosted on GitHub/blob for this test.
#
# Prereqs:
#   - Azure CLI 2.61+   (az bicep bundled)
#   - az login  &&  az account set --subscription <SUB_ID>
#   - Deployer needs Owner or User Access Administrator on the subscription (role assignments).
#
# Usage:
#   bash scripts/create-templatespec-stack.sh [RG] [LOCATION] [SPEC_NAME] [VERSION]

set -euo pipefail

RG="${1:-rg-crowdstrike-ts}"
LOCATION="${2:-westus2}"
SPEC_NAME="${3:-crowdstrike-falcon-stack-sub}"
VERSION="${4:-1.0}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_BICEP="$REPO_ROOT/crowdstrike-fcs-azure-bicep-generated/cs-deployment-subscription.bicep"
ENGINE_JSON="$REPO_ROOT/dist/cs-deployment-subscription.json"
WRAPPER_BICEP="$REPO_ROOT/stacks/stackWrapper.inline.subscription.bicep"
WRAPPER_JSON="$REPO_ROOT/dist/stackWrapper.inline.subscription.json"
FORM_JSON="$REPO_ROOT/ui/uiFormDefinition.templatespec.json"

echo "==> [0/4] Build portal forms from ui/base (adds the Prerequisites checks)"
python3 "$REPO_ROOT/scripts/form-checks/build_forms.py"

echo "==> [1/4] Build engine template  (dist/cs-deployment-subscription.json)"
mkdir -p "$REPO_ROOT/dist"
az bicep build --file "$ENGINE_BICEP" --outfile "$ENGINE_JSON"

echo "==> [2/4] Build stack wrapper (inlines the engine via loadJsonContent)"
# IMPORTANT: engine JSON must exist first - loadJsonContent embeds it at compile time.
az bicep build --file "$WRAPPER_BICEP" --outfile "$WRAPPER_JSON"

echo "==> [3/4] Ensure resource group '$RG' in '$LOCATION'"
az group create --name "$RG" --location "$LOCATION" --output none

echo "==> [4/4] Publish Template Spec '$SPEC_NAME' v'$VERSION' (wrapper + Form)"
az ts create \
  --name "$SPEC_NAME" \
  --version "$VERSION" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --template-file "$WRAPPER_JSON" \
  --ui-form-definition "$FORM_JSON" \
  --yes \
  --output none

TS_ID="$(az ts show --name "$SPEC_NAME" --version "$VERSION" --resource-group "$RG" --query id -o tsv)"

echo ""
echo "===================================================================="
echo " Template Spec published. Test the stack-creating UI in the portal:"
echo ""
echo "   https://portal.azure.com/#@/resource${TS_ID}/deploy"
echo ""
echo " Or: Portal > Template specs > $SPEC_NAME > $VERSION > Deploy"
echo "===================================================================="
echo ""
echo "After deploying, confirm the stack exists:"
echo "  az stack sub list -o table"
echo "  az stack sub show --name <prefix>crowdstrike-falcon-<env><suffix> -o json"
echo ""
echo "Tear down the test (deletes the stack; detached resources remain):"
echo "  az stack sub delete --name <stack-name> --action-on-unmanage deleteAll --yes"
echo ""
echo "Re-publish after editing the form or wrapper (bump the version):"
echo "  bash scripts/create-templatespec-stack.sh \"$RG\" \"$LOCATION\" \"$SPEC_NAME\" 1.1"