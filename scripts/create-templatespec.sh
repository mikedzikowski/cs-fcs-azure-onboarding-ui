#!/usr/bin/env bash
#
# Create a Template Spec with a portal Form (uiFormDefinition) so you can test the
# CrowdStrike Falcon onboarding UI in the REAL Azure portal (not the flaky sandbox).
#
# Prereqs:
#   - Azure CLI 2.61+  (az bicep is bundled; `az bicep version` to check)
#   - Logged in:  az login
#   - Set an active subscription:  az account set --subscription <SUB_ID>
#
# Usage:
#   ./scripts/create-templatespec.sh [RESOURCE_GROUP] [LOCATION] [SPEC_NAME] [VERSION]
#
# Defaults shown below. Re-run with a new VERSION to publish an updated form.

set -euo pipefail

RG="${1:-rg-crowdstrike-ts}"
LOCATION="${2:-westus2}"
SPEC_NAME="${3:-crowdstrike-falcon-sub}"
VERSION="${4:-1.0}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BICEP_SRC="$REPO_ROOT/crowdstrike-fcs-azure-bicep-generated/cs-deployment-subscription.bicep"
TEMPLATE_JSON="$REPO_ROOT/dist/cs-deployment-subscription.json"
FORM_JSON="$REPO_ROOT/ui/uiFormDefinition.templatespec.json"

echo "==> Build portal forms from ui/base (adds the Prerequisites checks)"
python3 "$REPO_ROOT/scripts/form-checks/build_forms.py"

echo "==> Building ARM JSON from Bicep"
mkdir -p "$REPO_ROOT/dist"
az bicep build --file "$BICEP_SRC" --outfile "$TEMPLATE_JSON"

echo "==> Ensuring resource group '$RG' exists in '$LOCATION'"
az group create --name "$RG" --location "$LOCATION" --output none

echo "==> Creating/updating Template Spec '$SPEC_NAME' version '$VERSION'"
az ts create \
  --name "$SPEC_NAME" \
  --version "$VERSION" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --template-file "$TEMPLATE_JSON" \
  --ui-form-definition "$FORM_JSON" \
  --yes \
  --output none

TS_ID="$(az ts show --name "$SPEC_NAME" --version "$VERSION" --resource-group "$RG" --query id -o tsv)"

echo ""
echo "==> Done. Template Spec version id:"
echo "    $TS_ID"
echo ""
echo "Test the form in the portal:"
echo "  1. Portal > search 'Template specs' > open '$SPEC_NAME' > version '$VERSION' > Deploy"
echo "  OR open this deep link:"
echo "  https://portal.azure.com/#@/resource${TS_ID}/deploy"
echo ""
echo "To publish an updated form after editing ui/uiFormDefinition.templatespec.json:"
echo "  ./scripts/create-templatespec.sh \"$RG\" \"$LOCATION\" \"$SPEC_NAME\" 1.1"