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
  that checks resource providers, the user's roles and blocking storage policies, and blocks Next
  until the role/provider checks pass (or the user skips them), then collects only the inputs that
  apply, including an optional existing storage account for the deployment scripts.
* Two delivery options, same files:
  * **Template Spec**: `az ts create --template-file <wrapper.json> --ui-form-definition <form.json>`.
  * **Deploy to Azure button**: the compiled JSON in `deploy/` served from raw GitHub, opened with
    `https://portal.azure.com/#view/Microsoft_Azure_CreateUIDef/CustomDeploymentBlade/uri/<enc template>/uiFormDefinitionUri/<enc form>`.
    This URL format isn't in Microsoft's Deploy-to-Azure docs (Microsoft sample repos use it).
    The documented `#create/Microsoft.Template/uri/<enc template>` link would skip the form and its
    checks, so the repo deliberately doesn't offer it.
    The button needs ARM JSON; it can't load remote Bicep.

Two scopes, kept at parity: **subscription** and **management group / tenant root**. The wrapper
names the stack `cs-subscription-stack` / `cs-managementgroup-stack`, the fixed names CrowdStrike's
deprovisioning steps use (one stack per scope).

## Layout

| Path | What it is | Edit? |
|---|---|---|
| `crowdstrike-fcs-azure-bicep-generated/` | CrowdStrike's public engine (`cs-deployment-subscription.bicep`, `cs-deployment-management-group.bicep`, modules, PowerShell callback scripts). Upstream: `github.com/CrowdStrike/azure-bicep-cloud-registration`. | **No.** Replace the folder wholesale when a new bundle ships. |
| `stacks/stackWrapper.inline.{subscription,managementGroup}.bicep` | Wrapper: declares the deployment stack, inlines the compiled engine via `loadJsonContent('../dist/...')`, passes form outputs through as engine parameters. | Yes, keep the two in step. |
| `ui/base/uiFormDefinition.templatespec*.json` | Hand-written form source (CrowdStrike, Features, Advanced tabs). | Yes. |
| `scripts/form-checks/checks.py` | Builders for the checks (providers, GA, UAA/Owner/Stack Owner, storage policy, monitored-subscription Owner), the skip-checks option, the passed-box style, the Falcon IP field and the deployment-script storage section. | Yes. |
| `scripts/form-checks/build_forms.py` | Builds `ui/uiFormDefinition.templatespec*.json` from `ui/base/` + `checks.py`: adds the Prerequisites and Scope tabs, rebuilds the shared CrowdStrike/Features tabs identically for both forms, rewrites outputs. | Yes. |
| `ui/uiFormDefinition.templatespec*.json` | **Generated** forms. | No, regenerate. |
| `deploy/` | **Generated** button payload: compiled wrappers + forms with stable names. Served publicly from raw GitHub. | No, regenerate with `make-deploy-button.sh --stage`. |
| `scripts/create-templatespec-stack.sh`, `...-stack-mg.sh` | Build forms → `az bicep build` engine → build wrapper → publish a Template Spec version. | |
| `scripts/make-deploy-button.sh` | `--stage` copies build output into `deploy/` and **scans it** (refuses on GUIDs other than the allowlisted built-in role and policy IDs, 32-hex strings, 12-digit numbers, key/SAS material). Without `--stage` prints button Markdown for a base URL. | |
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
* **The prerequisite checks are optional.** `checks.skip_checks()` adds a `skipChecks` CheckBox
  (unticked by default) and a Warning InfoBox as the last two elements of the Prerequisites tab in
  both forms. `checks.or_skipped(ok)` wraps a rule as `or(steps('basics').skipChecks, ok)`.
  * Wrapped: every Prerequisites-tab check rule, and the Scope-tab monitored-subscription Owner
    rule. The checks still run and show their result; only the blocking is lifted.
  * Never wrapped (they're inputs, not checks): the MG form's "Select a management group above.",
    the Advanced-tab storage rules, and the Falcon IP / credentials / Object ID validations.
  * New check rules must be wrapped with `or_skipped()`.
  * Don't set `defaultValue` on a CheckBox: the 2021-09-09 schema doesn't allow it (unchecked
    already outputs false). `isInitialRegistration` in `ui/base` predates this and still has one.
  * Seen in the portal (warning when ticked). Continuing past a failing check hasn't been exercised.
* Role detection uses `GET {scope}/providers/Microsoft.Authorization/permissions`:
  UAA = actions contain `Microsoft.Authorization/*` and `*/read`; Owner = `*` with no notActions;
  Deployment Stack Owner = `Microsoft.Resources/deploymentStacks/*`. **Owner does not imply the
  other two**; each is checked separately (verified by removing roles from a test account).
* Global Administrator check: **both forms** (`checks.global_admin("basics")`). Subscription form:
  elements `rp_elems + ga_elems + perm_elems`, rule on the `resourceScope` subscription selector.
  Management-group form: elements `ga_elems + mg_perm_elems + ...`, rule on the
  `csInfraSubscription` selector right after "Select a management group". Skippable like every check.
  It's inferred from a plain `GET /providers/microsoft.aadiam/diagnosticSettings` (no Graph from
  forms). Don't route it through `/batch` (that broke it). For non-admins it stays amber
  "Confirming…" rather than red. (It was removed in `f6e20c3` and restored, subscription first, then
  management group, on request.)
* Storage policy check (`checks.storage_policy_info`, both forms, Prerequisites tab): one GET of
  `policyAssignments?$filter=atScope()` on the deployment / infrastructure subscription (inherited
  assignments included). Looks only for an assignment of the built-in IDs in `STORAGE_POLICIES`
  (restrict network access + its ARO variant, public access disallowed). **Information only, by
  request: no validation rule, never blocks Next**; the warning recommends an existing storage
  account or a policy exemption. "Loaded" is `contains(response, 'value')` (an empty list is a real
  answer). The three definition IDs are in `make-deploy-button.sh`'s GUID allowlist. Verified in the
  portal 2026-11-25 with the public-access policy assigned (Audit and Deny).
* Passed checks: `checks.passed()` = InfoBox style `None` + "✅ " prefix. The 2021-09-09 schema has no
  green/success style (Info, Warning, Error, None only). Verified in the portal.
* Monitored-subscription Owner check uses ARM `/batch` (names required; >20 requests turn async).
* Existing deployment-script storage (Advanced tab, `checks.script_storage_section`):
  * The wrapper maps `deploymentScriptStorageAccountId` / `deploymentScriptSubnetId` to the engine's
    `deploymentScriptSettings` (null when unused). No subnet = `listKeys()` in the wrapper, and the
    stack then stores that key readable in its parameters (the form warns). Keep the stack's
    `parameters` a literal object: wrapping it in `union()`/`if()` made preflight fail with
    "Expected Object but got String". The wrapper `fail()`s on a subnet without a storage account
    and on a malformed storage account ID.
  * Shown only when the engine runs a script at that scope (`SCRIPTS_RUN_SUB` = real-time
    visibility; `SCRIPTS_RUN_MG` = any feature, because MG scope also runs the scope lookup).
  * Form view validations exist only on TextBox (schema 2021-09-09); CheckBox and ResourceSelector
    take only `required`. So every storage/subnet rule sits on a read-only `storageCheck` TextBox
    whose `defaultValue` is the selected account's name, not on the optional subnet box.
  * ResourceSelector filters with `scope: {subscriptionId}` (schema), not createUiDefinition's
    `options.filter`. The existing-Event-Hub selector in `ui/base` still uses `options.filter`; it
    deploys, so the portal accepts it, but it isn't in the schema.
  * Verified 2026-11-25 (lab, West US): both forms in the portal (every storage/subnet rule, pass and
    fail), then full registrations with parameters computed from the served forms' outputs:
    subscription key path, and management group private path (public access disabled, private
    endpoint for `file` + `privatelink.file.core.windows.net`, delegated subnet with a NAT gateway,
    no key). The scripts used the chosen storage account; nothing was auto-created.
  * With public access disabled a `Microsoft.Storage` service endpoint is not enough; the subnet
    needs a private endpoint + DNS zone (Microsoft: "Run Bicep deployment script privately over a
    private endpoint").
  * In an automated (chrome-devtools) browser, Review + create never finished final validation and
    Create stayed disabled, for `main`'s form too. Validate/deploy from the CLI with parameters
    evaluated from the form's `view.outputs` instead; don't conclude the form is broken.
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
* The stack name is fixed per scope: `cs-subscription-stack` / `cs-managementgroup-stack`, the
  names CrowdStrike's deprovisioning steps (`az stack ... delete --name ...`) expect. Don't derive it
  from env/prefix/suffix.
* **Updates** re-run the same form at the same scope (same stack name, in-place update) with the
  same env/prefix/suffix (otherwise the engine's resource names change). The form doesn't
  prefill current settings, and
  `stackActionOnUnmanage` defaults to `detachAll`: dropped features leave detached resources behind.
* `azurePrincipalId` must be the CrowdStrike **enterprise application Object ID** (the engine
  assigns roles with `principalType: 'ServicePrincipal'`), not the Application ID.

## Testing

There is no unit-test suite. Changes are verified by:

1. `python3 scripts/form-checks/build_forms.py` succeeds and both forms parse as JSON. Also validate
   both against Microsoft's published schema
   (`https://schema.management.azure.com/schemas/2021-09-09/uiFormDefinition.schema.json`, e.g. with
   Python `jsonschema`). Two known, already-deployed exceptions: `isInitialRegistration`'s CheckBox
   `defaultValue` and the existing-Event-Hub selector's `options.filter`. Anything else is new.
2. Driving the form in the portal (Template Spec, or the button URL pinned to a commit SHA so the
   5-minute raw-GitHub cache can't serve an old copy): every check in pass and fail states, then
   Review + create, then **Create**, then watching the stack:
   `az stack sub show -n cs-subscription-stack` or
   `az stack mg show --management-group-id <mg> -n cs-managementgroup-stack`.
   The deployment script logs (callbacks to Falcon) live in the stack's resource group.
   If **Create** won't enable (seen in automated browsers), evaluate the served form's
   `view.outputs` with the inputs you entered, check them against the Review + create summary, and
   deploy the served wrapper with those parameters from the CLI. That's how the 2026-11-25
   end-to-end tests were run. Pass secrets on the command line only; never write them to a file.
3. Offline checks used so far (kept outside the repo): a small evaluator for the Form view expression
   subset to run every `isValid`/`visible` rule against simulated portal states, and a JSON-schema
   validation against the published 2021-09-09 schema.
4. For button changes: push, confirm the raw URLs return 200 with `access-control-allow-origin: *`,
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
* Raw GitHub caches each file ~5 minutes (`cache-control: max-age=300`): after a push, `main` can
  still serve the old form. Use the commit SHA in the URL to check, or wait.
* A new or changed Deny policy assignment can take ~30 minutes to start denying (Microsoft). A
  deployment right after assigning one may still succeed.
* The portal can restore a form's earlier selections (for example a ticked skip checkbox) after a
  reload in the same session. Re-check the Prerequisites tab before concluding anything.
* `deleteAll` on a stack removes `rg-cs-<env>`, but not the diagnostic settings the stack didn't
  manage (`cs-aad-to-eventhub`, `cs-monitor-activity-to-eventhub`); CrowdStrike's deprovisioning
  script removes those.

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
