#!/usr/bin/env python3
"""Build the Template Spec portal forms in ui/ from the hand-written forms in ui/base/.

Edit ui/base/*.json (or checks.py), then run:  python3 scripts/form-checks/build_forms.py
The create-templatespec-stack*.sh scripts run this before publishing.

Both forms get a first "Prerequisites" tab that checks resource providers and the
deploying user's permissions, and blocks Next / Review + create until every check passes.
The CrowdStrike service principal object ID (with an InfoBox on which ID to use) and, for
subscription scope, the subscriptions to monitor move to a second "Scope" tab.
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checks  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EL = " " * 12  # indent of a step element in the form files


class Form:
    def __init__(self, path):
        self.text = open(path).read()
        self.lines = self.text.split("\n")
        self.data = json.loads(self.text)
        self.b_start = self.lines.index('          "name": "basics",')
        self.b_elems = self.lines.index('          "elements": [', self.b_start)
        self.b_end = self.lines.index("          ]", self.b_elems)
        assert self.lines[self.b_end + 1] == "        },"
        self.blocks = self._blocks(self.b_elems + 1, self.b_end)
        self.elements = {e["name"]: e for e in self.data["view"]["properties"]["steps"][0]["elements"]}
        assert list(self.blocks) == list(self.elements), (list(self.blocks), list(self.elements))

    def _blocks(self, start, end):
        """Original text of each basics element, so untouched elements keep their formatting."""
        blocks, cur = {}, None
        for line in self.lines[start:end]:
            if line == EL + "{":
                cur = [line]
            elif cur is not None:
                cur.append(line)
                if line in (EL + "}", EL + "},"):
                    cur[-1] = EL + "}"
                    blocks[next(x for x in cur if '"name":' in x).split('"')[3]] = cur
                    cur = None
        return blocks

    def keep(self, name):
        return self.blocks[name]

    def edited(self, name, validations=(), text=None):
        """An existing element with blocking validations appended (and optionally new InfoBox text)."""
        e = copy.deepcopy(self.elements[name])
        if text:
            e["options"]["text"] = text
        if validations:
            c = e.setdefault("constraints", {})
            c["validations"] = c.get("validations", []) + [
                {"isValid": f"[{ok}]", "message": msg} for ok, msg in validations
            ]
        return dump(e)

    def build(self, basics, scope, output_replacements):
        def join(blocks):
            out = []
            for i, b in enumerate(blocks):
                out += b[:-1] + [b[-1] + ("," if i < len(blocks) - 1 else "")]
            return out

        assert self.lines[self.b_start + 1] == '          "label": "Basics",'
        scope_step = ["        {", '          "name": "scope",', '          "label": "Scope",', '          "elements": ['] \
            + join(scope) + ["          ]", "        },"]
        out = self.lines[:self.b_start + 1] + ['          "label": "Prerequisites",'] \
            + self.lines[self.b_start + 2:self.b_elems + 1] + join(basics) \
            + self.lines[self.b_end:self.b_end + 2] + scope_step + self.lines[self.b_end + 2:]
        text = "\n".join(out)
        for old, new in output_replacements:
            assert text.count(old) == 1, old
            text = text.replace(old, new)
        json.loads(text)
        return text


def dump(obj):
    return [EL + line for line in json.dumps(obj, indent=2, ensure_ascii=False).splitlines()]


def dumps(objs):
    return [dump(o) for o in objs]


# The template assigns Azure roles to azurePrincipalId (principalId with principalType
# 'ServicePrincipal'), so it must be the enterprise application's (service principal's) object
# ID. CrowdStrike's app is multi-tenant, so the customer tenant has only the enterprise
# application (no app registration). A stale ID (the app deleted and re-consented) or the
# app's client ID makes the role assignments target the wrong object.
PRINCIPAL_HELP = ("Enter the Object ID of the CrowdStrike enterprise application (not the Application ID). "
                  "Find it in Entra ID > Enterprise applications > cs-app-… > Overview.")
PRINCIPAL_DOCS = "https://learn.microsoft.com/entra/identity/enterprise-apps/application-properties#object-id"


def principal_id(f):
    """The base form's azurePrincipalId TextBox, relabelled, with an InfoBox above it."""
    e = copy.deepcopy(f.elements["azurePrincipalId"])
    e["label"] = "CrowdStrike enterprise application – Object ID (service principal)"
    e["toolTip"] = ("The Object ID of the CrowdStrike enterprise application (service principal) in Entra ID — not its "
                    "Application (client) ID.")
    info = {"name": "azurePrincipalIdInfo", "type": "Microsoft.Common.InfoBox", "visible": True,
            "options": {"style": "Info", "text": PRINCIPAL_HELP, "uri": PRINCIPAL_DOCS}}
    # Echo the exact ID the deployment will use. Form expressions have no regex, so "looks like
    # a GUID" is approximated as 36 characters in five dash-separated groups.
    v = "coalesce(steps('scope').azurePrincipalId, '')"
    echo = checks.box(
        "azurePrincipalIdEcho", f"and(equals(length({v}), 36), equals(length(split({v}, '-')), 5))", "Info",
        f"[concat('Roles will be assigned to principal ID ', {v}, '.')]")
    return dumps([info, e, echo])


# ---------------------------------------------------------------------------------------------
# Tabs after Scope are shared by both forms, so the subscription and management-group options
# can't drift apart. The subscription base form's Features tab is the single source; the CrowdStrike
# engine accepts the same feature parameters at both scopes (incl. logIngestionSettings).
# ---------------------------------------------------------------------------------------------
SUB_BASE = os.path.join(ROOT, "ui/base/uiFormDefinition.templatespec.json")

# The engine requires Falcon API credentials when either of these is deployed
# (cs-deployment-*.bicep: validatedFalconClientID / validatedFalconClientSecret):
#   shouldDeployLogIngestion        = enableRealTimeVisibility
#   shouldDeployScanningEnvironment = enableDspm || enableVulnerabilityScanning
NEEDS_CREDS = ("or(steps('features').enableRealTimeVisibility, steps('features').enableDspm, "
               "steps('features').enableVulnerabilityScanning)")


def shared_tabs(text):
    """Rebuild the CrowdStrike and Features tabs (and their outputs) identically for both forms."""
    d = json.loads(text)
    sub = json.load(open(SUB_BASE))
    steps = {s["name"]: s for s in d["view"]["properties"]["steps"]}
    sub_steps = {s["name"]: s for s in sub["view"]["properties"]["steps"]}

    # CrowdStrike tab: only the Falcon cloud and Azure cloud type. The credentials move to Features.
    cs = steps["crowdStrikeConfig"]
    creds = {e["name"]: e for e in cs["elements"] if e["name"] in ("falconClientId", "falconClientSecret")}
    cs["elements"] = [e for e in cs["elements"] if e["name"] not in ("credsInfo", "falconClientId", "falconClientSecret")]

    # Features tab: the subscription base's controls (incl. "Use an existing Event Hub"), then the
    # Falcon API credentials, shown and required only when a feature that needs them is selected.
    features = copy.deepcopy(sub_steps["features"]["elements"])
    # The existing-Event-Hub lookups build their path from the selected namespace. Without a
    # namespace they call "/eventhubs?..." (400 InvalidBatchRequestUrl), and a failed lookup keeps
    # Create disabled. Only run them once the option is on and the inputs exist (ArmApiControl
    # "condition" in the Form view schema).
    eh_on = "and(steps('features').enableRealTimeVisibility, steps('features').useExistingEventHub, not(empty(steps('features').existingEh.ehNamespace.id)))"
    lookup_needs = {
        "hubsApi": eh_on,
        "activityCgApi": f"and({eh_on}, not(empty(steps('features').existingEh.activityHubName)))",
        "entraCgApi": f"and({eh_on}, not(empty(steps('features').existingEh.entraHubName)))",
    }
    for section in features:
        for e in section.get("elements", []):
            if e["name"] in lookup_needs:
                e["condition"] = f"[{lookup_needs[e['name']]}]"
    client_id = copy.deepcopy(creds["falconClientId"])
    secret = copy.deepcopy(creds["falconClientSecret"])
    client_id["constraints"]["required"] = f"[{NEEDS_CREDS}]"
    secret["constraints"]["required"] = f"[{NEEDS_CREDS}]"
    features.append({
        "name": "falconApi",
        "type": "Microsoft.Common.Section",
        "label": "Falcon API credentials",
        "visible": f"[{NEEDS_CREDS}]",
        "elements": [
            {"name": "falconApiInfo", "type": "Microsoft.Common.InfoBox", "visible": True,
             "options": {"style": "Info", "text": "Real-time visibility, DSPM and vulnerability scanning report to Falcon, so a Falcon API client ID and secret are required."}},
            client_id,
            secret,
        ],
    })
    # Falcon IP addresses for the Event Hub firewall: entered by the user (as in CrowdStrike's
    # Terraform module), shown and required with real-time visibility.
    rtv = "steps('features').enableRealTimeVisibility"
    features.insert(next(i for i, e in enumerate(features) if e["name"] == "falconApi") if any(e["name"] == "falconApi" for e in features) else len(features),
                    checks.falcon_ip_section("features", "steps('crowdStrikeConfig').falconApiFqdn", rtv))
    steps["features"]["elements"] = features

    # Outputs: credentials come from the Features section, empty when no feature needs them; the
    # existing-Event-Hub choice is passed at both scopes.
    out = d["view"]["outputs"]["parameters"]
    out["falconClientId"] = f"[if({NEEDS_CREDS}, steps('features').falconApi.falconClientId, '')]"
    out["falconClientSecret"] = f"[if({NEEDS_CREDS}, steps('features').falconApi.falconClientSecret, '')]"
    out["logIngestionSettings"] = copy.deepcopy(sub["view"]["outputs"]["parameters"]["logIngestionSettings"])
    out["falconIpAddresses"] = checks.falcon_ip_output("features", rtv)

    # InfoBox uses options.style (schema); some base boxes still say "icon".
    def fix(o):
        if isinstance(o, dict):
            if o.get("type") == "Microsoft.Common.InfoBox" and "icon" in o.get("options", {}):
                o["options"]["style"] = o["options"].pop("icon")
            for v in o.values():
                fix(v)
        elif isinstance(o, list):
            for v in o:
                fix(v)
    fix(d)
    return json.dumps(d, indent=2, ensure_ascii=False) + "\n"


def subscription_form():
    f = Form(os.path.join(ROOT, "ui/base/uiFormDefinition.templatespec.json"))
    # Subscription-scope Form views must start with a Microsoft.Common.ResourceScope named
    # resourceScope (schema: only allowed as the first element of the first step). Without it
    # the portal cannot build the deployment ("element for [steps('basics').resourceScope
    # .location.name] could not be found" / "'location' property must be specified").
    # Layout copied from the Form view sandbox's own autogenerated subscription-scope form.
    sub = "steps('basics').resourceScope.subscription.subscriptionId"
    where = "deployment subscription"

    rp_elems, rp_ok = checks.providers("basics", sub, where)
    ga_elems, ga_ok = checks.global_admin("basics")
    perm_elems, perm = checks.permissions("basics", "permDeploySub", f"concat('/subscriptions/', {sub})", where, "dep")
    mon_elems, mon_ok = checks.monitored_owner("scope", "steps('scope').subscriptionIds", sub)

    basics = [
        dump({
            "name": "resourceScope",
            "type": "Microsoft.Common.ResourceScope",
            "subscription": {"constraints": {"validations": [
                {"isValid": f"[{ok}]", "message": msg} for ok, msg in [
                    (rp_ok, "Required resource providers are missing (or still being checked) in this subscription. See the resource provider message below."),
                    (ga_ok, "Global Administrator is required (or is still being checked). See the Global Administrator message below."),
                    (perm["uaa"], "User Access Administrator is required on this subscription (or is still being checked). See the message below."),
                    (perm["owner"], "Owner is required on this subscription (or is still being checked). See the Owner message below."),
                    (perm["stack"], "Azure Deployment Stack Owner is required on this subscription (or is still being checked). See the message below."),
                ]]}},
            "location": {
                "label": f.elements["location"]["label"],
                "toolTip": f.elements["location"]["toolTip"],
                "allowedValues": [v["value"] for v in f.elements["location"]["constraints"]["allowedValues"]],
            },
        }),
        f.edited("intro", text="Prerequisite check for CrowdStrike Falcon Cloud Security. Select the subscription and region the deployment runs in; this page then verifies the required resource providers and your permissions. You cannot continue until every check passes."),
    ] + dumps(rp_elems + ga_elems + perm_elems)

    scope = principal_id(f) + [
        f.edited("subscriptionIds", validations=[
            (mon_ok, "Owner is required on every subscription to monitor (or is still being checked). See the Owner message below."),
        ]),
    ] + dumps(mon_elems)

    return shared_tabs(f.build(basics, scope, [
        # Same normalisation as the Owner check (no spaces, no empty entries), so what is
        # checked is what gets deployed.
        ('''"subscriptionIds": "[if(empty(steps('basics').subscriptionIds), parse('[]'), split(steps('basics').subscriptionIds, ','))]",''',
         '''"subscriptionIds": "[if(empty(steps('scope').subscriptionIds), parse('[]'), filter(split(replace(steps('scope').subscriptionIds, ' ', ''), ','), (s) => not(empty(s))))]",'''),
        ('''"azurePrincipalId": "[steps('basics').azurePrincipalId]",''',
         '''"azurePrincipalId": "[steps('scope').azurePrincipalId]",'''),
        # Deployment context: same expressions the sandbox generator emits for subscription scope.
        ('''"subscriptionId": "[steps('basics').targetSubscription.subscriptionId]",
      "location": "[steps('basics').location]",''',
         '''"subscriptionId": "[steps('basics').resourceScope.subscription.id]",
      "location": "[steps('basics').resourceScope.location.name]",'''),
        ('''"csInfraSubscriptionId": "[steps('basics').targetSubscription.subscriptionId]",''',
         '''"csInfraSubscriptionId": "[steps('basics').resourceScope.subscription.subscriptionId]",'''),
        ('''"location": "[steps('basics').location]",
        "azurePrincipalId"''',
         '''"location": "[steps('basics').resourceScope.location.name]",
        "azurePrincipalId"'''),
    ]))


def management_group_form():
    f = Form(os.path.join(ROOT, "ui/base/uiFormDefinition.templatespec.managementGroup.json"))
    # Same layout the form view sandbox generates for a managementGroupDeploymentTemplate: a
    # ResourceScope first (renders the management group picker + Region), with the deployment
    # context read from resourceScope.managementGroup.id and resourceScope.location.name.
    # last(split(..., '/')) yields the plain group ID whether .id is a name or a resource path.
    mg = "last(split(coalesce(steps('basics').resourceScope.managementGroup.id, ''), '/'))"
    infra = "steps('basics').csInfraSubscription.subscriptionId"

    ga_elems, ga_ok = checks.global_admin("basics")
    # Owner on the management group is inherited by every subscription under it, so it
    # covers all monitored subscriptions without a per-subscription call.
    mg_perm_elems, mg_perm = checks.permissions(
        "basics", "permMg", f"concat('/providers/Microsoft.Management/managementGroups/', {mg})",
        "management group", "mg")
    rp_elems, rp_ok = checks.providers("basics", infra, "infrastructure subscription")
    infra_perm_elems, infra_perm = checks.permissions(
        "basics", "permInfra", f"concat('/subscriptions/', {infra})",
        "infrastructure subscription", "infra", checks=("owner",))

    region = f.elements["region"]
    basics = [
        dump({
            "name": "resourceScope",
            "type": "Microsoft.Common.ResourceScope",
            "location": {
                "label": region["label"],
                "toolTip": region["toolTip"],
                "allowedValues": [v["value"] for v in region["constraints"]["allowedValues"]],
            },
        }),
        f.edited("intro", text="Prerequisite check for CrowdStrike Falcon Cloud Security at management-group scope. Select the management group, region and infrastructure subscription; this page then verifies the required resource providers and your permissions. You cannot continue until every check passes."),
        # ResourceScope has no management group constraints in the schema, so every blocking
        # rule for this tab sits on the (required) infrastructure subscription picker.
        dump({
            "name": "csInfraSubscription",
            "type": "Microsoft.Common.SubscriptionSelector",
            "label": "Infrastructure subscription",
            "toolTip": f.elements["csInfraSubscriptionId"]["toolTip"],
            "constraints": {"validations": [
                {"isValid": f"[{ok}]", "message": msg} for ok, msg in [
                    (f"not(empty({mg}))", "Select a management group above."),
                    (ga_ok, "Global Administrator is required (or is still being checked). See the Global Administrator message below."),
                    (mg_perm["uaa"], "User Access Administrator is required on the management group (or is still being checked). See the message below."),
                    (mg_perm["owner"], "Owner is required on the management group (or is still being checked). See the Owner message below."),
                    (mg_perm["stack"], "Azure Deployment Stack Owner is required on the management group (or is still being checked). See the message below."),
                    (rp_ok, "Required resource providers are missing (or still being checked) in the infrastructure subscription. See the resource provider message below."),
                    (infra_perm["owner"], "Owner is required on the infrastructure subscription (or is still being checked). See the Owner message below."),
                ]]},
        }),
    ] + dumps(ga_elems + mg_perm_elems + rp_elems + infra_perm_elems)

    # Subscriptions outside the selected management group can be added (the engine's
    # subscriptionIds), with the same Owner check as the subscription form.
    mon_elems, mon_ok = checks.monitored_owner("scope", "steps('scope').subscriptionIds", infra, checks.NONE_MG)
    extra = copy.deepcopy(next(e for s in json.load(open(SUB_BASE))["view"]["properties"]["steps"]
                               if s["name"] == "basics" for e in s["elements"] if e["name"] == "subscriptionIds"))
    extra["label"] = "Additional subscriptions to monitor (comma-separated)"
    extra["toolTip"] = ("Optional. Subscriptions outside the selected management group to monitor as well. "
                        "Every subscription under the management group is monitored automatically.")
    extra.setdefault("constraints", {})["validations"] = [
        {"isValid": f"[{mon_ok}]", "message": "Owner is required on every subscription to monitor (or is still being checked). See the Owner message below."}]
    scope = principal_id(f) + [dump(extra)] + dumps(mon_elems)

    old_mg_ids = '"managementGroupIds": "[parse(concat(\'[\\"\', steps(\'basics\').managementGroupId, \'\\"]\'))]",'
    new_mg_ids = '"managementGroupIds": "[parse(concat(\'[\\"\', ' + mg + ', \'\\"]\'))]",'
    return shared_tabs(f.build(basics, scope, [
        ('''"azurePrincipalId": "[steps('basics').azurePrincipalId]",''',
         '''"azurePrincipalId": "[steps('scope').azurePrincipalId]",'''),
        # Deployment context: same expressions the sandbox generator emits for MG scope.
        ('''"managementGroupId": "[steps('basics').managementGroupId]",
      "location": "[steps('basics').region]",''',
         '''"managementGroupId": "[steps('basics').resourceScope.managementGroup.id]",
      "location": "[steps('basics').resourceScope.location.name]",'''),
        (old_mg_ids, new_mg_ids),
        ('''"subscriptionIds": "[parse('[]')]",''',
         '''"subscriptionIds": "[if(empty(steps('scope').subscriptionIds), parse('[]'), filter(split(replace(steps('scope').subscriptionIds, ' ', ''), ','), (s) => not(empty(s))))]",'''),
        ('''"csInfraSubscriptionId": "[steps('basics').csInfraSubscriptionId]",''',
         '''"csInfraSubscriptionId": "[steps('basics').csInfraSubscription.subscriptionId]",'''),
        ('''"location": "[steps('basics').region]",
        "azurePrincipalId"''',
         '''"location": "[steps('basics').resourceScope.location.name]",
        "azurePrincipalId"'''),
    ]))


if __name__ == "__main__":
    for name, build in [
        ("ui/uiFormDefinition.templatespec.json", subscription_form),
        ("ui/uiFormDefinition.templatespec.managementGroup.json", management_group_form),
    ]:
        with open(os.path.join(ROOT, name), "w") as out:
            out.write(build())
        print(f"built {name}")
