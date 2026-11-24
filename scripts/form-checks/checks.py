"""Prerequisite checks for the Template Spec portal forms (uiFormDefinition).

Each builder returns hidden ArmApiControl elements, the InfoBoxes that report the result,
and the expressions used for the blocking validations, so a box and the validation that
blocks Next can never disagree.

Form expressions can only call Azure Resource Manager (no Microsoft Graph), and an
ArmApiControl output is empty both while loading and (as far as we can tell) after a
failed call. So every check has an explicit "still checking" state, and still-checking
counts as failing for the validations.
"""

import json

PERMS_API = "/providers/Microsoft.Authorization/permissions?api-version=2022-04-01"
RBAC_DOCS = "https://learn.microsoft.com/azure/role-based-access-control/role-assignments-portal"
STACK_DOCS = "https://learn.microsoft.com/azure/azure-resource-manager/bicep/deployment-stacks#deployment-stack-permissions"
RP_DOCS = "https://learn.microsoft.com/azure/azure-resource-manager/management/resource-providers-and-types#register-resource-provider"

# Providers the stack needs that ARM does not auto-register (deployment scripts create a
# container instance and storage account behind the scenes).
NAMESPACES = [
    ("rpManagement", "Microsoft.Management"),
    ("rpContainerInstance", "Microsoft.ContainerInstance"),
    ("rpStorage", "Microsoft.Storage"),
    ("rpResources", "Microsoft.Resources"),
    ("rpInsights", "Microsoft.Insights"),
    ("rpPolicyInsights", "Microsoft.PolicyInsights"),
    ("rpEventHub", "Microsoft.EventHub"),
]


def box(name, visible, style, text, uri=None):
    opts = {"style": style, "text": text}
    if uri:
        opts["uri"] = uri
    return {"name": name, "type": "Microsoft.Common.InfoBox", "visible": f"[{visible}]", "options": opts}


def arm_get(name, path):
    return {"name": name, "type": "Microsoft.Solutions.ArmApiControl", "request": {"method": "GET", "path": path}}


def providers(step, sub, where):
    """Registration state of NAMESPACES in subscription `sub` (an expression)."""
    state = lambda c: f"steps('{step}').{c}.registrationState"
    missing = lambda c: f"and(not(empty({state(c)})), not(equals({state(c)}, 'Registered')))"
    loaded = "and(" + ", ".join(f"not(empty({state(c)}))" for c, _ in NAMESPACES) + ")"
    any_missing = "or(" + ", ".join(missing(c) for c, _ in NAMESPACES) + ")"
    missing_list = ", ".join(f"if({missing(c)}, concat('{ns} (', {state(c)}, ')  '), '')" for c, ns in NAMESPACES)
    elements = [
        arm_get(c, f"[concat('/subscriptions/', {sub}, '/providers/{ns}?api-version=2021-04-01')]")
        for c, ns in NAMESPACES
    ] + [
        box("rpCheckPending", f"and(not({loaded}), not({any_missing}))", "Info",
            f"Checking resource provider registration in the {where}... If this message does not clear, the check could not run - verify manually with: az provider show --namespace <namespace> --query registrationState"),
        box("rpCheckPassed", f"and({loaded}, not({any_missing}))", "Info",
            f"All resource providers enabled - every required resource provider is registered in the {where}."),
        box("rpCheckMissing", f"{any_missing}", "Error",
            f"[concat('Missing resource providers - please enable them in the {where} before deploying, or the deployment stack will fail:  ', {missing_list}, ' Register each with: az provider register --namespace <namespace> --subscription ', {sub}, ' --wait   then reload this form.')]",
            RP_DOCS),
    ]
    return elements, f"and({loaded}, not({any_missing}))"


def global_admin(step):
    """Global Administrator, inferred from reading tenant-level Entra ID diagnostic settings
    (the resource the template needs that role for). Plain GET: the /batch variant did not
    return a usable result inside the portal.
    Used by the subscription form only; the management-group form has no Global Administrator check."""
    out = f"coalesce(steps('{step}').gaCheck, parse('{{}}'))"
    ok = f"contains({out}, 'value')"
    denied = f"contains({out}, 'error')"
    elements = [
        arm_get("gaCheck", "/providers/microsoft.aadiam/diagnosticSettings?api-version=2017-04-01"),
        box("gaCheckPending", f"and(not({ok}), not({denied}))", "Warning",
            "Confirming Global Administrator... If this message does not change to 'confirmed' within a few seconds, your account could not read Entra ID diagnostic settings, which requires Global Administrator. Assign or activate the role (PIM), then sign out of the Azure portal, sign back in and reopen this form (role changes can take up to 10 minutes to apply)."),
        box("gaCheckPassed", ok, "Info",
            "Global Administrator confirmed (able to read Entra ID diagnostic settings)."),
        box("gaCheckMissing", denied, "Error",
            "Missing Global Administrator - you need the Global Administrator role in Entra ID to configure Entra ID log export. Assign or activate the role (PIM), then sign out of the Azure portal, sign back in and reopen this form (role changes can take up to 10 minutes to apply).",
            RBAC_DOCS),
    ]
    return elements, ok


def permissions(step, ctl, scope_path, where, prefix, gate=None, checks=("uaa", "owner", "stack")):
    """Effective permissions (includes group and inherited assignments) at `scope_path`, an
    expression yielding e.g. /subscriptions/<id>. `gate` must be true before results count
    (used to require that a typed-in management group actually exists)."""
    P = f"steps('{step}').{ctl}.value"
    loaded = f"and({gate}, not(empty({P})))" if gate else f"not(empty({P}))"
    any_entry = lambda cond: f"not(empty(filter({P}, (p) => {cond})))"
    has = {
        # The User Access Administrator role itself is required; Owner does not count. Only that
        # role's definition pairs these two actions (Owner is just '*'). The "Elevate access"
        # toggle assigns this role at tenant root, so it is inherited here and also counts.
        "uaa": any_entry("and(contains(p.actions, 'Microsoft.Authorization/*'), contains(p.actions, '*/read'))"),
        "owner": any_entry("and(contains(p.actions, '*'), empty(p.notActions))"),
        # CrowdStrike requires the Azure Deployment Stack Owner role itself; Owner alone is not
        # enough. Only that role's definition contains this action (Owner is just '*', and
        # Azure Deployment Stack Contributor lists individual stack actions instead).
        "stack": any_entry("contains(p.actions, 'Microsoft.Resources/deploymentStacks/*')"),
    }
    text = {
        "uaa": (f"User Access Administrator confirmed on the {where}.",
                f"Missing User Access Administrator - assign the User Access Administrator role on the {where} (Owner alone is not enough), or activate it in PIM, then sign out of the Azure portal, sign back in and reopen this form (role changes can take up to 10 minutes to apply).",
                RBAC_DOCS),
        "owner": (f"Owner confirmed on the {where}.",
                  f"Missing Owner - you need Owner on the {where}. Assign Owner (or activate it in PIM), then sign out of the Azure portal, sign back in and reopen this form (role changes can take up to 10 minutes to apply).",
                  RBAC_DOCS),
        "stack": (f"Azure Deployment Stack Owner confirmed on the {where}.",
                  f"Missing Azure Deployment Stack Owner - assign the Azure Deployment Stack Owner role on the {where} (Owner alone is not enough), then sign out of the Azure portal, sign back in and reopen this form (role changes can take up to 10 minutes to apply).",
                  STACK_DOCS),
    }
    elements = [
        arm_get(ctl, f"[concat({scope_path}, '{PERMS_API}')]"),
        box(f"{prefix}PermPending", f"and({gate}, not({loaded}))" if gate else f"not({loaded})", "Info",
            f"Checking your permissions on the {where}... If this message does not clear, your account may have no access to it."),
    ]
    oks = {}
    for c in checks:
        passed, missing, uri = text[c]
        name = f"{prefix}{c.capitalize()}"
        elements += [
            box(f"{name}Passed", f"and({loaded}, {has[c]})", "Info", passed),
            box(f"{name}Missing", f"and({loaded}, not({has[c]}))", "Error", missing, uri),
        ]
        oks[c] = f"and({loaded}, {has[c]})"
    return elements, oks


def management_group_exists(step, mg):
    """The permissions API answers even for a management group that does not exist (with
    permissions inherited from tenant root), so confirm the group itself first."""
    name = f"steps('{step}').mgLookup.name"
    ok = f"and(not(empty({mg})), equals(toLower(coalesce({name}, '')), toLower({mg})))"
    elements = [
        arm_get("mgLookup", f"[concat('/providers/Microsoft.Management/managementGroups/', {mg}, '?api-version=2023-04-01')]"),
        box("mgLookupPending", f"and(not(empty({mg})), not({ok}))", "Warning",
            f"[concat('Looking up management group ', {mg}, '... If this message does not clear, the management group does not exist or your account cannot read it. Use the management group ID, not its display name.')]"),
        box("mgLookupPassed", ok, "Info", f"[concat('Management group ', {mg}, ' found.')]"),
    ]
    return elements, ok


SKIPPED = "steps('basics').skipChecks"


def skip_checks():
    """Opt-out for when a check is wrong for this user (e.g. Security Administrator rather than
    Global Administrator) or never finishes loading. Unticked by default; the checks still run
    and show their result, only the blocking rules are lifted (see or_skipped)."""
    return [
        {
            "name": "skipChecks",
            "type": "Microsoft.Common.CheckBox",
            "label": "Skip the prerequisite checks (I have confirmed the requirements myself)",
            "toolTip": "Lets you continue while a check is failing or still loading. The deployment fails if a requirement is really missing.",
        },
        box("skipChecksWarning", SKIPPED, "Warning",
            "Prerequisite checks skipped. If a resource provider or role is really missing, the deployment stack fails partway through. "
            "CrowdStrike requires Owner and Azure Deployment Stack Owner on the deployment scope, and Global Administrator or "
            "Security Administrator in Entra ID when real-time visibility creates the Entra ID diagnostic setting."),
    ]


def or_skipped(ok):
    """A prerequisite-check rule that also passes when the user ticked skipChecks. Only for
    prerequisite checks, never for input validation."""
    return f"or({SKIPPED}, {ok})"


NONE_SUB = "No additional subscriptions listed - only the deployment subscription will be monitored (Owner was checked on the Prerequisites tab)."
NONE_MG = "No additional subscriptions listed - every subscription under the selected management group is monitored (Owner on the management group was checked on the Prerequisites tab)."


def monitored_owner(step, ids, exclude_sub, none_text=NONE_SUB):
    """Owner on each subscription in the comma-separated `ids` box, via one /batch call.
    NOTE: not yet confirmed in the portal - the /batch call failed for the GA check there."""
    mon_all = f"filter(split(toLower(replace(coalesce({ids}, ''), ' ', '')), ','), (s) => not(empty(s)))"
    # Excludes the deployment subscription (checked on its own; a duplicate request name
    # would fail the whole batch).
    mon = f"filter({mon_all}, (s) => not(equals(s, toLower({exclude_sub}))))"
    R = f"coalesce(steps('{step}').permMonitored.responses, parse('[]'))"
    owner_sig = '"actions":["*"],"dataActions":[],"notActions":[]'
    failing = f"map(filter({R}, (r) => not(and(equals(r.httpStatusCode, 200), contains(string(r.content.value), '{owner_sig}')))), (r) => r.name)"
    count = f"length({mon})"
    loaded = f"equals(length({R}), {count})"
    elements = [
        {
            "name": "permMonitored",
            "type": "Microsoft.Solutions.ArmApiControl",
            "request": {
                "method": "POST",
                "path": "/batch?api-version=2020-06-01",
                "body": {
                    "requests": f"[map({mon}, (s) => parse(concat('{{\"name\":\"', s, '\",\"httpMethod\":\"GET\",\"url\":\"/subscriptions/', s, '{PERMS_API}\"}}')))]"
                },
            },
        },
        box("ownerMonNone", f"equals({count}, 0)", "Info", none_text),
        box("ownerMonPending", f"and(greater({count}, 0), not({loaded}))", "Info",
            "Checking Owner on the subscriptions to monitor... If this message does not clear, the check could not run - it supports up to 20 subscriptions, in this tenant, with no duplicates."),
        box("ownerMonPassed", f"and(greater({count}, 0), {loaded}, empty({failing}))", "Info",
            "Owner confirmed on every subscription to monitor."),
        box("ownerMonMissing", f"and(greater({count}, 0), {loaded}, not(empty({failing})))", "Error",
            f"[concat('Missing Owner permissions - you need Owner on every subscription CrowdStrike will monitor. Missing or not accessible on:  ', string({failing}), '  Assign Owner (or activate it in PIM), then sign out of the Azure portal, sign back in and reopen this form (role changes can take up to 10 minutes to apply).')]",
            RBAC_DOCS),
    ]
    return elements, f"or(equals({count}, 0), and({loaded}, empty({failing})))"


# Falcon IP addresses for the Event Hub firewall. Like CrowdStrike's Terraform module
# (falcon_ip_addresses), the user enters them; they are not stored in this repo. Each Falcon
# cloud's "Allow CrowdStrike IP addresses" page (Falcon login required) lists them.
IP_DOCS = {
    "api.crowdstrike.com": ("US-1", "https://docs.crowdstrike.com/access?ft:originId=ibc7ee4c"),
    "api.us-2.crowdstrike.com": ("US-2", "https://docs.crowdstrike.com/access?ft:originId=a1f2fdef"),
    "api.eu-1.crowdstrike.com": ("EU-1", "https://docs.crowdstrike.com/access?ft:originId=yf3ab7b3"),
}
IP_RE = r"(\d{1,3}\.){3}\d{1,3}(/\d{1,2})?"


def falcon_ip_section(step, fqdn, visible):
    """Features-tab section: Falcon IP addresses, shown and required when `visible`."""
    boxes = [box(f"ipDocs{label.replace('-', '')}", f"equals({fqdn}, '{host}')", "Info",
                 f"Enter the Falcon {label} IP addresses from CrowdStrike's \"Allow CrowdStrike IP addresses\" page (opens the {label} docs; Falcon login required). The Event Hub firewall denies everything else, so without them real-time visibility receives no logs.",
                 uri)
             for host, (label, uri) in IP_DOCS.items()]
    known = "or(" + ", ".join(f"equals({fqdn}, '{h}')" for h in IP_DOCS) + ")"
    boxes.append(box("ipDocsOther", f"not({known})", "Info",
                     "Enter the Falcon IP addresses for your Falcon cloud from CrowdStrike's \"Allow CrowdStrike IP addresses\" documentation page (Falcon login required). The Event Hub firewall denies everything else."))
    return {
        "name": "falconIps",
        "type": "Microsoft.Common.Section",
        "label": "Falcon IP addresses",
        "visible": f"[{visible}]",
        "elements": boxes + [{
            "name": "falconIpAddresses",
            "type": "Microsoft.Common.TextBox",
            "label": "Falcon IP addresses (comma-separated)",
            "placeholder": "e.g. 192.0.2.10, 192.0.2.11",
            "toolTip": "CrowdStrike Falcon IP addresses allowed through the Event Hub firewall.",
            "constraints": {
                "required": f"[{visible}]",
                "validations": [{"regex": f"^\\s*{IP_RE}(\\s*,\\s*{IP_RE})*\\s*$",
                                 "message": "Comma-separated IPv4 addresses (optionally /CIDR), e.g. 192.0.2.10, 192.0.2.11."}],
            },
        }],
    }


def falcon_ip_output(step, visible):
    v = f"steps('{step}').falconIps.falconIpAddresses"
    return f"[if({visible}, filter(split(replace(coalesce({v}, ''), ' ', ''), ','), (s) => not(empty(s))), parse('[]'))]"


# Existing storage account for the engine's deployment scripts (engine parameter
# deploymentScriptSettings). Requirements from CrowdStrike's README ("Storage account requirements
# for deploymentScriptSettings") and Microsoft's docs (deployment-script-develop "Use an existing
# storage account"; container-instances-virtual-network-concepts):
#   * storage account in csInfraSubscriptionId, allowSharedKeyAccess true (unset means true),
#     no firewall rules (networkAcls.defaultAction Allow), a kind/SKU pair with Azure Files;
#   * publicNetworkAccess Disabled is only reachable from a subnet (CrowdStrike: subnetId is needed
#     when the account isn't reachable from a public or service-endpoint-allowed network path);
#   * a subnet in the same subscription, delegated to Microsoft.ContainerInstance/containerGroups,
#     in the deployment region. Container groups in a VNet need a NAT gateway for outbound traffic
#     and a Microsoft.Storage service endpoint; the form can't verify those, the info box says so.
SCRIPT_STORAGE_DOCS = "https://github.com/CrowdStrike/azure-bicep-cloud-registration#deployment-fails-because-the-auto-created-deployment-script-storage-account-violates-policy"
ACI_DELEGATION = "Microsoft.ContainerInstance/containerGroups"


def script_storage_section(step, infra, location, enabled):
    """Advanced-tab option and section; returns (elements, outputs).

    `infra`: infrastructure subscription ID expression; `location`: deployment region expression;
    `enabled`: true when the engine runs deployment scripts at this scope.
    Form view validations exist only on TextBox (schema 2021-09-09), and an empty optional TextBox
    may not be validated, so every rule sits on `storageCheck`: a read-only TextBox whose value is
    the selected storage account's name, so it always has a value once a storage account is picked."""
    on = f"and({enabled}, steps('{step}').useExistingScriptStorage)"
    s = f"steps('{step}').scriptStorage"
    sa_id = f"coalesce({s}.storageAccount.id, '')"
    subnet = f"replace(coalesce({s}.subnetId, ''), ' ', '')"
    infra_prefix = f"concat('/subscriptions/', {infra}, '/')"
    in_infra = lambda rid: f"startsWith(toLower({rid}), toLower({infra_prefix}))"
    sa = f"{s}.storageApi"
    sa_loaded = f"not(empty(coalesce({sa}.name, '')))"
    sku = f"coalesce({sa}.sku.name, '')"
    kind = f"coalesce({sa}.kind, '')"
    # Microsoft's supported pairs: Premium_LRS/ZRS + FileStorage; Standard_LRS/GRS/RAGRS + Storage or
    # StorageV2; Standard_ZRS/GZRS/RAGZRS + StorageV2.
    kind_sku_ok = (f"or(and(startsWith({sku}, 'Premium_'), equals({kind}, 'FileStorage')), "
                   f"and(contains(parse('[\"Standard_LRS\",\"Standard_GRS\",\"Standard_RAGRS\"]'), {sku}), "
                   f"contains(parse('[\"Storage\",\"StorageV2\"]'), {kind})), "
                   f"and(contains(parse('[\"Standard_ZRS\",\"Standard_GZRS\",\"Standard_RAGZRS\"]'), {sku}), equals({kind}, 'StorageV2')))")
    public_off = f"equals(coalesce({sa}.properties.publicNetworkAccess, 'Enabled'), 'Disabled')"
    sa_rules = [
        (in_infra(sa_id), "The storage account must be in the infrastructure subscription (deployment scripts only accept a storage account from their own subscription)."),
        (f"or(not({sa_loaded}), not(equals({sa}.properties.allowSharedKeyAccess, false)))",
         "The storage account has shared key access disabled. Deployment scripts need allowSharedKeyAccess = true, even with a subnet."),
        (f"or(not({sa_loaded}), not(equals(coalesce({sa}.properties.networkAcls.defaultAction, 'Allow'), 'Deny')))",
         "The storage account has firewall rules (default action Deny). CrowdStrike's template doesn't support storage firewalls; use publicNetworkAccess Disabled with a subnet instead."),
        (f"or(not({sa_loaded}), {kind_sku_ok})",
         "This storage account's kind and SKU don't support Azure file shares. Use StorageV2 with a Standard SKU, or FileStorage with a Premium SKU."),
        (f"or(not({sa_loaded}), not({public_off}), not(empty({subnet})))",
         "Public network access is disabled on this storage account, so the script can only reach it from a virtual network. Enter a delegated subnet."),
    ]
    sn = f"{s}.subnetApi"
    sn_loaded = f"not(empty(coalesce({sn}.name, '')))"
    vnet = f"{s}.vnetApi"
    vnet_loaded = f"not(empty(coalesce({vnet}.location, '')))"
    sn_delegated = f"contains(map(coalesce({sn}.properties.delegations, parse('[]')), (d) => d.properties.serviceName), '{ACI_DELEGATION}')"
    # The VNet is the subnet ID without its last two segments (/subnets/<name>).
    vnet_id = f"substring({subnet}, 0, lastIndexOf(toLower({subnet}), '/subnets/'))"
    subnet_rules = [
        (f"or(empty({subnet}), {in_infra(subnet)})", "The subnet must be in the infrastructure subscription."),
        (f"or(empty({subnet}), contains(toLower({subnet}), '/subnets/'))", "Enter the subnet's full resource ID (…/virtualNetworks/<vnet>/subnets/<subnet>)."),
        (f"or(empty({subnet}), {sn_loaded})", "Still reading the subnet (or it couldn't be read - check the resource ID and your access)."),
        (f"or(empty({subnet}), not({sn_loaded}), {sn_delegated})", f"The subnet isn't delegated to {ACI_DELEGATION}."),
        (f"or(empty({subnet}), not({vnet_loaded}), equals(toLower({vnet}.location), toLower({location})))",
         "The subnet's virtual network must be in the deployment region (the script's container instance runs there)."),
    ]
    rules = ([(f"or(empty({sa_id}), {sa_loaded})", "Still reading the storage account (or it couldn't be read).")]
             + sa_rules + subnet_rules)
    elements = [
        {"name": "useExistingScriptStorage", "type": "Microsoft.Common.CheckBox",
         "label": "Use an existing storage account for deployment scripts",
         "visible": f"[{enabled}]",
         "toolTip": "The CrowdStrike deployment scripts run in an Azure Container Instance and normally create their own storage account with public network access. Use this if a policy blocks that account."},
        {"name": "scriptStorage", "type": "Microsoft.Common.Section", "label": "Deployment script storage",
         "visible": f"[{on}]",
         "elements": [
             {"name": "scriptStorageInfo", "type": "Microsoft.Common.InfoBox", "visible": True,
              "options": {"style": "Info", "uri": SCRIPT_STORAGE_DOCS, "text":
                  "Use a storage account in the infrastructure subscription with shared key access enabled and no firewall rules. "
                  "If public network access is disabled on it, also enter a subnet in the deployment region delegated to "
                  f"{ACI_DELEGATION}, so the script runs in that virtual network. That subnet needs a NAT gateway for outbound "
                  "traffic and a Microsoft.Storage service endpoint (Azure Container Instances requirements the form can't check)."}},
             {"name": "storageAccount", "type": "Microsoft.Solutions.ResourceSelector", "label": "Storage account",
              "resourceType": "Microsoft.Storage/storageAccounts",
              "toolTip": "Existing storage account in the infrastructure subscription.",
              "scope": {"subscriptionId": f"[{infra}]"},
              "constraints": {"required": f"[{on}]"}},
             {**arm_get("storageApi", f"[concat({sa_id}, '?api-version=2023-05-01')]"),
              "condition": f"[and({on}, not(empty({sa_id})))]"},
             {"name": "subnetId", "type": "Microsoft.Common.TextBox", "label": "Subnet resource ID (optional)",
              "placeholder": "/subscriptions/<id>/resourceGroups/<rg>/providers/Microsoft.Network/virtualNetworks/<vnet>/subnets/<subnet>",
              "toolTip": f"Optional unless public network access is disabled on the storage account. A subnet delegated to {ACI_DELEGATION}. With a subnet, the script mounts the storage with its managed identity and no key is passed.",
              "constraints": {"required": False}},
             {**arm_get("subnetApi", f"[concat({subnet}, '?api-version=2024-05-01')]"),
              "condition": f"[and({on}, not(empty({subnet})), contains(toLower({subnet}), '/subnets/'))]"},
             {**arm_get("vnetApi", f"[concat({vnet_id}, '?api-version=2024-05-01')]"),
              "condition": f"[and({on}, not(empty({subnet})), contains(toLower({subnet}), '/subnets/'))]"},
             # Carries every rule above: it always has a value once a storage account is selected.
             {"name": "storageCheck", "type": "Microsoft.Common.TextBox", "label": "Selected storage account",
              "readOnly": True,
              "defaultValue": f"[coalesce({s}.storageAccount.name, '')]",
              "toolTip": "The storage account the deployment scripts will use. The checks below run against it.",
              "constraints": {"required": f"[{on}]",
                              "validations": [{"isValid": f"[or(not({on}), {ok})]", "message": msg} for ok, msg in rules]}},
             box("scriptStorageKeyWarning", f"and({on}, empty({subnet}))", "Warning",
                 "Without a subnet, the deployment looks up this storage account's access key and passes it to the CrowdStrike template. "
                 "It is then readable in the deployment stack's parameters by anyone who can read the stack. Enter a delegated subnet "
                 "to avoid passing a key, or rotate the key after deploying."),
             box("scriptStorageOk", f"and({on}, not(empty({sa_id})), {sa_loaded}, " + ", ".join(ok for ok, _ in sa_rules + subnet_rules) + ")", "Info",
                 "Storage account meets the deployment script requirements the form can check."),
         ]},
    ]
    outputs = {
        "deploymentScriptStorageAccountId": f"[if({on}, {sa_id}, '')]",
        # The engine compares the subscription segment case-sensitively against csInfraSubscriptionId.
        "deploymentScriptSubnetId": f"[if(and({on}, not(empty({subnet}))), concat({infra_prefix}, substring({subnet}, length({infra_prefix}), sub(length({subnet}), length({infra_prefix})))), '')]",
    }
    return elements, outputs
