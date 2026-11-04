#!/usr/bin/env bash
#
# Print "Deploy to Azure" buttons (Markdown) for the subscription- and management-group-scope
# deployment-stack wrappers, with the Prerequisites portal form attached.
#
# Two link formats are printed for each scope:
#
#   1. WITH the portal form (Form view / uiFormDefinition, the same JSON the Template Spec uses):
#        https://portal.azure.com/#view/Microsoft_Azure_CreateUIDef/CustomDeploymentBlade
#            /uri/<encoded template URL>/uiFormDefinitionUri/<encoded form URL>
#      Not in Microsoft's deploy-button article, but used by Microsoft's own public
#      accelerators (Azure Monitor Baseline Alerts, Enterprise-Scale/ALZ, AVD accelerator,
#      Mission LZ) for subscription-, management-group- and tenant-scope templates.
#
#   2. WITHOUT a form (the only format Microsoft's deploy-button article documents):
#        https://portal.azure.com/#create/Microsoft.Template/uri/<encoded template URL>
#      The portal builds a generic parameter page from the template. No prerequisite checks.
#
# The button only works if every referenced file is publicly readable (raw GitHub URL on a
# public repo, or a blob URL with a read-only SAS). Anything referenced here becomes public:
# run with --stage first, which copies the build output into deploy/ and refuses to continue
# if it finds IDs that look like tenant/subscription/principal IDs, CIDs or client IDs.
#
# Usage:
#   scripts/make-deploy-button.sh [--stage] [BASE_URL] [SAS_TOKEN]
#
#   BASE_URL   URL of the folder holding the four deploy/ files. Default:
#              https://raw.githubusercontent.com/OWNER/REPO/refs/tags/TAG/deploy
#   SAS_TOKEN  optional, without the leading '?'. Appended to every file URL (blob hosting).
#   --stage    copy dist/ + ui/ build output into deploy/ (stable names) and scan it.
#   PORTAL     env var, default https://portal.azure.com (portal.azure.us for US Gov).
#
# Examples:
#   scripts/make-deploy-button.sh --stage
#   scripts/make-deploy-button.sh https://raw.githubusercontent.com/OWNER/REPO/refs/tags/v1.6/deploy

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="$REPO_ROOT/deploy"
PORTAL="${PORTAL:-https://portal.azure.com}"

STAGE=0
if [[ "${1:-}" == "--stage" ]]; then STAGE=1; shift; fi
BASE_URL="${1:-https://raw.githubusercontent.com/OWNER/REPO/refs/tags/TAG/deploy}"
BASE_URL="${BASE_URL%/}"
SAS="${2:-}"
SAS="${SAS#\?}"

# source in repo                                          -> published name in deploy/
FILES=(
  "dist/stackWrapper.inline.subscription.json|stackWrapper.subscription.json"
  "ui/uiFormDefinition.templatespec.json|uiFormDefinition.subscription.json"
  "dist/stackWrapper.inline.managementGroup.json|stackWrapper.managementGroup.json"
  "ui/uiFormDefinition.templatespec.managementGroup.json|uiFormDefinition.managementGroup.json"
)

# GUIDs allowed in published files: Azure built-in role definition IDs the engine assigns,
# plus all-zero placeholders. Anything else blocks staging.
ALLOWED_GUIDS="acdd72a7-3385-48ef-bd42-f606fba81ae7 69566ab7-960f-475b-8e7c-b3118f30c6bd
a638d3c7-ab3a-418d-83e6-5f17a39d4fde 4633458b-17de-408a-b874-0445c86b69e6
749f88d5-cbae-40b8-bcfc-e573ddc772fa f526a384-b230-433a-b45c-95f59c4a2dec
00000000-0000-0000-0000-000000000000"
# Reader, Storage File Data Privileged Contributor, Azure Event Hubs Data Receiver,
# Key Vault Secrets User, Monitoring Contributor, Azure Event Hubs Data Owner, placeholder.

scan() {  # scan FILE... ; non-zero exit on findings
  local bad=0 f g
  for f in "$@"; do
    for g in $(grep -o -i -E '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' "$f" | tr 'A-F' 'a-f' | sort -u); do
      if ! grep -q -w -- "$g" <<<"$ALLOWED_GUIDS"; then
        echo "  BLOCKED: $(basename "$f"): GUID not in allowlist (tenant/subscription/principal/client ID?)" >&2
        bad=1
      fi
    done
    # 32-hex (CrowdStrike CID / client ID shape), with or without a -XX checksum suffix.
    if grep -q -i -E '(^|[^0-9a-f-])[0-9a-f]{32}(-[0-9a-f]{2})?([^0-9a-f-]|$)' "$f"; then
      echo "  BLOCKED: $(basename "$f"): 32-hex string (CID / client ID shape)" >&2; bad=1
    fi
    if grep -q -E '(^|[^0-9])[0-9]{12}([^0-9]|$)' "$f"; then
      echo "  BLOCKED: $(basename "$f"): 12-digit number (account ID shape)" >&2; bad=1
    fi
    if grep -q -i -E 'sig=|AccountKey=|SharedAccessKey=|-----BEGIN' "$f"; then
      echo "  BLOCKED: $(basename "$f"): key/SAS material" >&2; bad=1
    fi
  done
  return $bad
}

if [[ $STAGE -eq 1 ]]; then
  mkdir -p "$DEPLOY_DIR"
  staged=()
  for entry in "${FILES[@]}"; do
    src="$REPO_ROOT/${entry%%|*}"; dst="$DEPLOY_DIR/${entry##*|}"
    [[ -f "$src" ]] || { echo "missing $src - run scripts/create-templatespec-stack*.sh build first" >&2; exit 1; }
    python3 -I -c 'import json,sys; json.load(open(sys.argv[1]))' "$src"   # must be strict JSON
    cp "$src" "$dst"; staged+=("$dst")
  done
  echo "==> staged ${#staged[@]} files in deploy/; scanning for IDs that must not go public" >&2
  if ! scan "${staged[@]}"; then
    echo "==> scan FAILED - do not commit deploy/. Remove the values and rebuild." >&2; exit 2
  fi
  echo "==> scan passed (GUIDs are built-in role IDs only; no 32-hex, 12-digit or key material)." >&2
  echo "    The forms also carry CrowdStrike's published Falcon cloud IP allowlist - review before publishing." >&2
  echo >&2
fi

enc() { python3 -I -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }
url() { if [[ -n "$SAS" ]]; then echo "$BASE_URL/$1?$SAS"; else echo "$BASE_URL/$1"; fi; }

button() {  # button LABEL TEMPLATE_FILE FORM_FILE
  local t f
  t="$(enc "$(url "$2")")"; f="$(enc "$(url "$3")")"
  echo "### $1"
  echo
  echo "With the Prerequisites form:"
  echo
  echo "[![Deploy to Azure](https://aka.ms/deploytoazurebutton)]($PORTAL/#view/Microsoft_Azure_CreateUIDef/CustomDeploymentBlade/uri/$t/uiFormDefinitionUri/$f)"
  echo
  echo "Template only (generic parameter page, no prerequisite checks):"
  echo
  echo "[![Deploy to Azure](https://aka.ms/deploytoazurebutton)]($PORTAL/#create/Microsoft.Template/uri/$t)"
  echo
}

button "Subscription scope"     stackWrapper.subscription.json    uiFormDefinition.subscription.json
button "Management group scope" stackWrapper.managementGroup.json uiFormDefinition.managementGroup.json
