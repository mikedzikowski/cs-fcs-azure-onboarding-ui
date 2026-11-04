#!/usr/bin/env bash
#
# Management-group counterpart of create-templatespec-stack.sh.
# Publishes a Template Spec whose template creates a MANAGEMENT-GROUP-scoped deployment stack,
# with the MG portal Form attached. Engine embedded inline (self-contained).
#
# Prereqs:
#   - Azure CLI 2.61+   (az bicep bundled)
#   - az login  &&  az account set --subscription <SUB_ID>   (spec is stored in this sub/RG)
#   - Deployer needs Owner/User Access Administrator at the target management group.
#
# Usage:
#   bash scripts/create-templatespec-stack-mg.sh [RG] [LOCATION] [SPEC_NAME] [VERSION]

set -euo pipefail

RG="${1:-rg-crowdstrike-ts}"
LOCATION="${2:-westus2}"
SPEC_NAME="${3:-crowdstrike-falcon-stack-mg}"
VERSION="${4:-1.0}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE_BICEP="$REPO_ROOT/crowdstrike-fcs-azure-bicep-generated/cs-deployment-management-group.bicep"
ENGINE_JSON="$REPO_ROOT/dist/cs-deployment-management-group.json"
WRAPPER_BICEP="$REPO_ROOT/stacks/stackWrapper.inline.managementGroup.bicep"
WRAPPER_JSON="$REPO_ROOT/dist/stackWrapper.inline.managementGroup.json"
FORM_JSON="$REPO_ROOT/ui/uiFormDefinition.templatespec.managementGroup.json"

echo "==> [0/4] Build portal forms from ui/base (adds the Prerequisites checks)"
python3 "$REPO_ROOT/scripts/form-checks/build_forms.py"

echo "==> [1/4] Build MG engine template (dist/cs-deployment-management-group.json)"
mkdir -p "$REPO_ROOT/dist"
az bicep build --file "$ENGINE_BICEP" --outfile "$ENGINE_JSON"

echo "==> [2/4] Build MG stack wrapper (inlines the engine via loadJsonContent)"
az bicep build --file "$WRAPPER_BICEP" --outfile "$WRAPPER_JSON"

echo "==> [3/4] Ensure resource group '$RG' in '$LOCATION' (stores the Template Spec)"
az group create --name "$RG" --location "$LOCATION" --output none

echo "==> [4/4] Publish Template Spec '$SPEC_NAME' v'$VERSION' (MG wrapper + Form)"
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
echo " MG Template Spec published. Test in the portal:"
echo "   https://portal.azure.com/#@/resource${TS_ID}/deploy"
echo "===================================================================="
echo ""
echo "Confirm the MG stack after deploying:"
echo "  az stack mg list --management-group-id <MG_ID> -o table"
echo ""
echo "Tear down:"
echo "  az stack mg delete --management-group-id <MG_ID> --name <stack-name> --action-on-unmanage deleteAll --yes"