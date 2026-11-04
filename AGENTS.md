# AGENTS.md

Orientation for coding agents working in this repo. Read this first, then `README.md` (user
guide) and `docs/prereq-checker.md` (how the checks work).

## What this repo is

A proof of concept (not a supported CrowdStrike product) that onboards Azure to CrowdStrike
Falcon Cloud Security from a **native Azure portal form** instead of the documented
"download the Bicep zip, upload to Cloud Shell, edit a `.bicepparam`, export the secret,
run `az stack ...`" flow.

* CrowdStrike's registration Bicep (`crowdstrike-fcs-azure-bicep-generated/`) is **unchanged**.
* A thin **stack wrapper** (`stacks/`) deploys that engine inside a
  `Microsoft.Resources/deploymentStacks` resource.
* A **portal form** (`uiFormDefinition`, Form view schema 2021-09-09) adds a *Prerequisites* tab
  that checks resource providers and the user's roles and blocks Next until they pass, then
  collects only the inputs that apply.
* Two delivery options, same files:
  * **Template Spec**: `az ts create --template-file <wrapper.json> --ui-form-definition <form.json>`.
  * **Deploy to Azure button**: the compiled JSON in `deploy/` served from raw GitHub, opened with
    `https://portal.azure.com/#view/Microsoft_Azure_CreateUIDef/CustomDeploymentBlade/uri/<enc template>/uiFormDefinitionUri/<enc form>`.
    This URL format isn't in Microsoft's Deploy-to-Azure docs (Microsoft sample repos use it).
    The documented `#create/Microsoft.Template/uri/<enc template>` link would skip the form and its
    checks, so the repo deliberately doesn't offer it.
    The button needs ARM JSON; it can't load remote Bicep.

Two scopes, kept at parity: **subscription** and **management group / tenant root**.

## Layout

| Path | What it is | Edit? |
|---|---|---|
| `crowdstrike-fcs-azure-bicep-generated/` | CrowdStrike's public engine (`cs-deployment-subscription.bicep`, `cs-deployment-management-group.bicep`, modules, PowerShell callback scripts). Upstream: `github.com/CrowdStrike/bicep-azure-cloud-registration`. | **No.** Replace the folder wholesale when a new bundle ships. |
| `stacks/stackWrapper.inline.{subscription,managementGroup}.bicep` | Wrapper: declares the deployment stack, inlines the compiled engine via `loadJsonContent('../dist/...')`, passes form outputs through as engine parameters. | Yes, keep the two in step. |
| `ui/base/uiFormDefinition.templatespec*.json` | Hand-written form source (CrowdStrike, Features, Advanced tabs). | Yes. |
| `scripts/form-checks/checks.py` | Builders for the checks (providers, GA, UAA/Owner/Stack Owner, monitored-subscription Owner) and the Falcon IP field. | Yes. |
| `scripts/form-checks/build_forms.py` | Builds `ui/uiFormDefinition.templatespec*.json` from `ui/base/` + `checks.py`: adds the Prerequisites and Scope tabs, rebuilds the shared CrowdStrike/Features tabs identically for both forms, rewrites outputs. | Yes. |
| `ui/uiFormDefinition.templatespec*.json` | **Generated** forms. | No, regenerate. |
| `deploy/` | **Generated** button payload: compiled wrappers + forms with stable names. Served publicly from raw GitHub. | No, regenerate with `make-deploy-button.sh --stage`. |
| `scripts/create-templatespec-stack.sh`, `...-stack-mg.sh` | Build forms → `az bicep build` engine → build wrapper → publish a Template Spec version. | |
| `scripts/make-deploy-button.sh` | `--stage` copies build output into `deploy/` and **scans it** (refuses on non-allowlisted GUIDs, 32-hex strings, 12-digit numbers, key/SAS material). Without `--stage` prints button Markdown for a base URL. | |
| `docs/prereq-checker.md` | Design and verification notes for every check. Keep it accurate when checks change. | Yes. |
| `docs/parameters.md` | Parameter reference. | Yes. |
| `docs/images/` | Screenshots used by README (IDs zeroed, a subscription name blurred). | Only with sanitised images. |

`dist/` (build output) is git-ignored; the publish scripts recreate it.

## Build and publish

```bash
# Forms only (fast; run after any change in ui/base or scripts/form-checks)
python3 scripts/form-checks/build_forms.py

# Template Spec (needs az login on the subscription that stores the spec; scripts don't pass --subscription)
bash scripts/create-templatespec-stack.sh    <RG> <REGION> crowdstrike-falcon-stack-sub <NEW_VERSION>
bash scripts/create-templatespec-stack-mg.sh <RG> <REGION> crowdstrike-falcon-stack-mg  <NEW_VERSION>

# Button payload (after the above has built dist/)
bash scripts/make-deploy-button.sh --stage
bash scripts/make-deploy-button.sh https://raw.githubusercontent.com/<owner>/<repo>/<ref>/deploy
```

Publish a new version number for each change so links to earlier versions keep working.

## How the form works (essentials)

* First element of the first step must be `Microsoft.Common.ResourceScope` named `resourceScope`
  (otherwise "'location' property must be specified"). Outputs read
  `steps('basics').resourceScope.subscription.id` / `.managementGroup.id` / `.location.name`.
* Checks are `Microsoft.Solutions.ArmApiControl` GETs made with the user's portal token, shown via
  `Microsoft.Common.InfoBox` (`options.style`, not `icon`), and enforced with
  `constraints.validations[].isValid` on the scope/subscription selector. "Still loading" counts as
  failing, so Next stays disabled until results arrive.
* Role detection uses `GET {scope}/providers/Microsoft.Authorization/permissions`:
  UAA = actions contain `Microsoft.Authorization/*` and `*/read`; Owner = `*` with no notActions;
  Deployment Stack Owner = `Microsoft.Resources/deploymentStacks/*`. **Owner does not imply the
  other two**; each is checked separately (verified by removing roles from a test account).
* Global Administrator is inferred from a plain `GET /providers/microsoft.aadiam/diagnosticSettings`
  (no Graph from forms). Don't route it through `/batch` (that broke it). For non-admins it stays
  amber "Confirming…" rather than red; Next is still blocked.
* Monitored-subscription Owner check uses ARM `/batch` (names required; >20 requests turn async).
* Gate optional lookups with ArmApiControl `condition` (e.g. the existing-Event-Hub lookups), or a
  failing call with empty inputs keeps **Create** disabled.
* DropDown `defaultValue` must be a **label**, not a value (e.g. `"Production"`, not `"prod"`).
* Features tab:
  * The Falcon API client ID/secret are shown and required only when real-time visibility, DSPM or
    vulnerability scanning is on. That mirrors the engine's own `validatedFalconClientID` rule.
  * The Falcon IP addresses are a user-entered, comma-separated field (shown and required with
    real-time visibility), like `falcon_ip_addresses` in CrowdStrike's Terraform module, with a
    link to the docs page for the selected Falcon cloud.
* The form **doesn't create the CrowdStrike enterprise application**. The customer must first run
  the Falcon onboarding wizard (create the Azure registration and grant admin consent), which
  creates `cs-app-…` in their tenant. The engine only assigns roles to `azurePrincipalId`.
* **Updates** re-run the same form at the same scope with the same env/prefix/suffix, which gives
  the same stack name and an in-place update. The form doesn't prefill current settings, and
  `stackActionOnUnmanage` defaults to `detachAll`: dropped features leave detached resources behind.
* `azurePrincipalId` must be the CrowdStrike **enterprise application Object ID** (the engine
  assigns roles with `principalType: 'ServicePrincipal'`), not the Application ID.

## Testing

There is no unit-test suite. Changes are verified by:

1. `python3 scripts/form-checks/build_forms.py` succeeds and both forms parse as JSON.
2. Publishing a new Template Spec version to a lab subscription and driving the form in the portal:
   every check in pass and fail states, then Review + create, then **Create**, then watching the stack:
   `az stack sub show -n <stack>` or `az stack mg show --management-group-id <mg> -n <stack>`.
   The deployment script logs (callbacks to Falcon) live in the stack's resource group.
3. For button changes: push, confirm the raw URLs return 200 with `access-control-allow-origin: *`,
   then open both buttons.

Known gotchas when testing:

* Role changes need a portal **sign-out/sign-in** (up to ~10 minutes) before the form sees them.
* `InvalidDeploymentLocation`: an earlier deployment with the same name ran in another region.
  Pick that region.
* `az account management-group list` silently registers `Microsoft.Management`, so don't run it
  while testing the provider check.
* The Falcon callback can return 409 ("Registration status invalid") depending on the tenant's
  registration state in Falcon and the *Initial registration* flag. That's a CrowdStrike-side
  behaviour, not a form bug.

**Verify, don't assume.** Ground role, provider and portal-behaviour claims in Microsoft/CrowdStrike
docs, the Bicep source, or a test. Several "obvious" assumptions here turned out wrong (Owner
covering Stack Owner, `/batch` for GA, DropDown defaults).

## Security rules (public repo)

This repository is **public**. Nothing tenant-specific may be committed, in code, docs, examples
or screenshots:

* CrowdStrike CIDs, customer/tenant IDs, Azure subscription/management-group/object IDs, API client
  IDs and secrets, tokens, keys, SAS, connection strings, real hostnames, public IPs (including
  Falcon IP allowlists), emails, user names.
* Use obvious placeholders: `00000000-0000-0000-0000-000000000000`, `<falcon-api-client-id>`,
  RFC 5737 IPs (`192.0.2.x`), `123456789012`.
* Real parameter files (`*.bicepparam` except `*.example.bicepparam`), `dist/`, `.env*`,
  screenshots of real tenants, and assistant/session history are git-ignored. Check with
  `git check-ignore -v <path>`.
* Stage files explicitly (never `git add -A` / `git add .`), then scan the **staged diff** for 32-hex
  strings, GUIDs outside the built-in role IDs, 12-digit numbers, IPv4 addresses, emails and
  hostnames before every push. `make-deploy-button.sh --stage` scans `deploy/`, not the rest of the tree.
* A commit that *removes* a value still exposes it in its diff. If something slips through, stop
  and report it; don't rewrite history without the owner's go-ahead.
