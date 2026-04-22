"""MCP server exposing QOD PPM button/wizard/workflow actions.

Design philosophy (see README):
  - Plain CRUD on `project.portfolio`, `project.program`, `project.project`,
    `project.task`, `ppm.risk`, `ppm.change.request`, etc. belongs in a
    *generic* Odoo MCP server. Run one alongside this one.
  - This server exposes only things CRUD can't — server methods that do
    non-trivial work when a button or wizard is invoked.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import OdooClient

mcp = FastMCP("qod-ppm")
_client: OdooClient | None = None


def client() -> OdooClient:
    global _client
    if _client is None:
        _client = OdooClient.from_env()
    return _client


def _read_state(model: str, rec_id: int, fields: list[str]) -> dict[str, Any]:
    rows = client().read(model, [rec_id], fields)
    if not rows:
        raise ValueError(f"{model} id={rec_id} not found")
    return rows[0]


# ---------------------------------------------------------------------------
# Milestones — state transitions on ppm.milestone
# ---------------------------------------------------------------------------

_MILESTONE_FIELDS = ["name", "state", "date_planned", "date_actual", "project_id"]


@mcp.tool()
def ppm_milestone_start(milestone_id: int) -> dict[str, Any]:
    """Transition a milestone from 'planned' to 'in_progress'."""
    client().call_action("ppm.milestone", "action_start", [milestone_id])
    return _read_state("ppm.milestone", milestone_id, _MILESTONE_FIELDS)


@mcp.tool()
def ppm_milestone_achieve(milestone_id: int) -> dict[str, Any]:
    """Mark a milestone as achieved; records today as the actual date."""
    client().call_action("ppm.milestone", "action_achieve", [milestone_id])
    return _read_state("ppm.milestone", milestone_id, _MILESTONE_FIELDS)


@mcp.tool()
def ppm_milestone_miss(milestone_id: int) -> dict[str, Any]:
    """Mark a milestone as missed."""
    client().call_action("ppm.milestone", "action_miss", [milestone_id])
    return _read_state("ppm.milestone", milestone_id, _MILESTONE_FIELDS)


@mcp.tool()
def ppm_milestone_cancel(milestone_id: int) -> dict[str, Any]:
    """Cancel a milestone."""
    client().call_action("ppm.milestone", "action_cancel", [milestone_id])
    return _read_state("ppm.milestone", milestone_id, _MILESTONE_FIELDS)


@mcp.tool()
def ppm_milestone_reopen(milestone_id: int) -> dict[str, Any]:
    """Reopen a milestone back to 'planned'."""
    client().call_action("ppm.milestone", "action_reopen", [milestone_id])
    return _read_state("ppm.milestone", milestone_id, _MILESTONE_FIELDS)


# ---------------------------------------------------------------------------
# Status Reports — wizard + publish/draft/print
# ---------------------------------------------------------------------------


@mcp.tool()
def ppm_status_report_generate(
    project_id: int,
    period: str | None = None,
    commentary: str | None = None,
) -> dict[str, Any]:
    """Run the Status Report wizard for a project.

    The wizard auto-populates RAG, budget, risks, milestones from project data
    and creates a `ppm.status.report` in draft state.

    Args:
        project_id: `project.project` id to report on.
        period: free-text period label (e.g. 'April 2026'); defaults to current month.
        commentary: optional commentary field.

    Returns:
        dict with the created status report id and summary fields.
    """
    vals: dict[str, Any] = {"project_id": project_id}
    if period:
        vals["period"] = period
    if commentary:
        vals["commentary"] = commentary
    wizard_id = client().execute_kw("ppm.status.report.wizard", "create", [vals])
    result = client().call_action("ppm.status.report.wizard", "action_create_report", [wizard_id])
    report_id = (result or {}).get("res_id") if isinstance(result, dict) else None
    if not report_id:
        # Fallback: most recently-created report for this project.
        rows = client().search_read(
            "ppm.status.report",
            [("project_id", "=", project_id)],
            ["id"],
            limit=1,
            order="id desc",
        )
        if not rows:
            raise RuntimeError("Wizard did not produce a status report")
        report_id = rows[0]["id"]
    return _read_state(
        "ppm.status.report",
        report_id,
        ["name", "state", "period", "project_id", "rag_overall"],
    )


@mcp.tool()
def ppm_status_report_publish(report_id: int) -> dict[str, Any]:
    """Publish a draft status report."""
    client().call_action("ppm.status.report", "action_publish", [report_id])
    return _read_state("ppm.status.report", report_id, ["name", "state", "project_id"])


@mcp.tool()
def ppm_status_report_reset_draft(report_id: int) -> dict[str, Any]:
    """Revert a published status report back to draft."""
    client().call_action("ppm.status.report", "action_reset_draft", [report_id])
    return _read_state("ppm.status.report", report_id, ["name", "state", "project_id"])


@mcp.tool()
def ppm_status_report_print_url(report_id: int) -> dict[str, Any]:
    """Return the Odoo URL for the PDF render of a status report.

    Odoo returns a report action; the caller fetches the PDF via that URL
    using the same credentials.
    """
    action = client().call_action("ppm.status.report", "action_print_report", [report_id])
    return {"report_id": report_id, "action": action}


# ---------------------------------------------------------------------------
# Change Requests — full workflow
# ---------------------------------------------------------------------------

_CR_FIELDS = ["name", "state", "project_id", "change_type", "priority", "initiator_id"]


@mcp.tool()
def ppm_change_request_submit(cr_id: int) -> dict[str, Any]:
    """Submit a draft Change Request for review; assigns a sequence number."""
    client().call_action("ppm.change.request", "action_submit", [cr_id])
    return _read_state("ppm.change.request", cr_id, _CR_FIELDS)


@mcp.tool()
def ppm_change_request_start_review(cr_id: int) -> dict[str, Any]:
    """Start review of a submitted Change Request."""
    client().call_action("ppm.change.request", "action_start_review", [cr_id])
    return _read_state("ppm.change.request", cr_id, _CR_FIELDS)


@mcp.tool()
def ppm_change_request_approve(cr_id: int) -> dict[str, Any]:
    """Approve a Change Request under review; creates a baseline snapshot."""
    client().call_action("ppm.change.request", "action_approve", [cr_id])
    return _read_state("ppm.change.request", cr_id, _CR_FIELDS)


@mcp.tool()
def ppm_change_request_reject(cr_id: int, reason: str) -> dict[str, Any]:
    """Reject a Change Request with a required reason (runs the reject wizard)."""
    wizard_id = client().execute_kw(
        "ppm.change.request.reject.wizard",
        "create",
        [{"change_request_id": cr_id, "reason": reason}],
    )
    client().call_action("ppm.change.request.reject.wizard", "action_confirm_reject", [wizard_id])
    return _read_state("ppm.change.request", cr_id, _CR_FIELDS)


@mcp.tool()
def ppm_change_request_reset_draft(cr_id: int) -> dict[str, Any]:
    """Return a submitted or rejected Change Request to draft."""
    client().call_action("ppm.change.request", "action_reset_draft", [cr_id])
    return _read_state("ppm.change.request", cr_id, _CR_FIELDS)


# ---------------------------------------------------------------------------
# Risks — workflow + P×I matrix
# ---------------------------------------------------------------------------

_RISK_FIELDS = [
    "name",
    "state",
    "risk_type",
    "probability",
    "impact",
    "risk_score",
    "risk_level",
    "project_id",
    "owner_id",
]


@mcp.tool()
def ppm_risk_start_analysis(risk_id: int) -> dict[str, Any]:
    """Transition a risk from 'identified' to 'analyzing'."""
    client().call_action("ppm.risk", "action_start_analysis", [risk_id])
    return _read_state("ppm.risk", risk_id, _RISK_FIELDS)


@mcp.tool()
def ppm_risk_start_mitigation(risk_id: int) -> dict[str, Any]:
    """Transition a risk to 'mitigating'."""
    client().call_action("ppm.risk", "action_start_mitigation", [risk_id])
    return _read_state("ppm.risk", risk_id, _RISK_FIELDS)


@mcp.tool()
def ppm_risk_start_monitoring(risk_id: int) -> dict[str, Any]:
    """Transition a risk to 'monitoring'."""
    client().call_action("ppm.risk", "action_start_monitoring", [risk_id])
    return _read_state("ppm.risk", risk_id, _RISK_FIELDS)


@mcp.tool()
def ppm_risk_mark_occurred(risk_id: int) -> dict[str, Any]:
    """Mark a risk as occurred."""
    client().call_action("ppm.risk", "action_mark_occurred", [risk_id])
    return _read_state("ppm.risk", risk_id, _RISK_FIELDS)


@mcp.tool()
def ppm_risk_close(risk_id: int) -> dict[str, Any]:
    """Close a risk; sets date_closed."""
    client().call_action("ppm.risk", "action_close", [risk_id])
    return _read_state("ppm.risk", risk_id, _RISK_FIELDS)


@mcp.tool()
def ppm_risk_reopen(risk_id: int) -> dict[str, Any]:
    """Reopen a closed risk back to 'identified'."""
    client().call_action("ppm.risk", "action_reopen", [risk_id])
    return _read_state("ppm.risk", risk_id, _RISK_FIELDS)


@mcp.tool()
def ppm_risk_move_in_matrix(risk_id: int, probability: int, impact: int) -> dict[str, Any]:
    """Move a risk in the P×I matrix.

    Both probability and impact are integers 1–5 (matching the selection keys).
    The server recomputes `risk_score` and `risk_level` automatically.
    """
    if not (1 <= probability <= 5) or not (1 <= impact <= 5):
        raise ValueError("probability and impact must be integers in [1, 5]")
    client().execute_kw(
        "ppm.risk",
        "write",
        [[risk_id], {"probability": str(probability), "impact": str(impact)}],
    )
    return _read_state("ppm.risk", risk_id, _RISK_FIELDS)


# ---------------------------------------------------------------------------
# Issues (risks flagged as issue_type) — separate sub-workflow
# ---------------------------------------------------------------------------

_ISSUE_FIELDS = [
    "name",
    "state",
    "issue_state",
    "project_id",
    "owner_id",
    "date_resolved",
]


@mcp.tool()
def ppm_issue_assign(issue_id: int) -> dict[str, Any]:
    """Move an issue from 'new' to 'assigned'."""
    client().call_action("ppm.risk", "action_issue_assign", [issue_id])
    return _read_state("ppm.risk", issue_id, _ISSUE_FIELDS)


@mcp.tool()
def ppm_issue_start(issue_id: int) -> dict[str, Any]:
    """Move an issue to 'in_progress'."""
    client().call_action("ppm.risk", "action_issue_start", [issue_id])
    return _read_state("ppm.risk", issue_id, _ISSUE_FIELDS)


@mcp.tool()
def ppm_issue_resolve(issue_id: int) -> dict[str, Any]:
    """Resolve an issue; sets date_resolved."""
    client().call_action("ppm.risk", "action_issue_resolve", [issue_id])
    return _read_state("ppm.risk", issue_id, _ISSUE_FIELDS)


@mcp.tool()
def ppm_issue_escalate(issue_id: int) -> dict[str, Any]:
    """Escalate an issue to management."""
    client().call_action("ppm.risk", "action_issue_escalate", [issue_id])
    return _read_state("ppm.risk", issue_id, _ISSUE_FIELDS)


# ---------------------------------------------------------------------------
# Role Assignments
# ---------------------------------------------------------------------------

_ROLE_FIELDS = ["name", "state", "role_id", "user_id", "project_id", "date_from", "date_to"]


@mcp.tool()
def ppm_role_activate(assignment_id: int) -> dict[str, Any]:
    """Activate a draft role assignment (syncs the security group)."""
    client().call_action("ppm.role.assignment", "action_activate", [assignment_id])
    return _read_state("ppm.role.assignment", assignment_id, _ROLE_FIELDS)


@mcp.tool()
def ppm_role_approve_and_activate(assignment_id: int) -> dict[str, Any]:
    """Approve and activate in one step."""
    client().call_action(
        "ppm.role.assignment", "action_approve_and_activate", [assignment_id]
    )
    return _read_state("ppm.role.assignment", assignment_id, _ROLE_FIELDS)


@mcp.tool()
def ppm_role_revoke(assignment_id: int) -> dict[str, Any]:
    """Revoke a role assignment; removes the user from the security group."""
    client().call_action("ppm.role.assignment", "action_revoke", [assignment_id])
    return _read_state("ppm.role.assignment", assignment_id, _ROLE_FIELDS)


@mcp.tool()
def ppm_role_reset_draft(assignment_id: int) -> dict[str, Any]:
    """Return a role assignment to draft."""
    client().call_action("ppm.role.assignment", "action_reset_draft", [assignment_id])
    return _read_state("ppm.role.assignment", assignment_id, _ROLE_FIELDS)


# ---------------------------------------------------------------------------
# Exports (wizards that emit XLSX attachments)
# ---------------------------------------------------------------------------


def _run_export_wizard(
    model: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    wizard_id = client().execute_kw(model, "create", [values])
    action = client().call_action(model, "action_export", [wizard_id])
    # action is `ir.actions.act_url` with /web/content/{attachment_id}?download=true
    return {"wizard": model, "action": action}


@mcp.tool()
def ppm_export_budget(
    project_id: int | None = None,
    portfolio_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    category_id: int | None = None,
    include_closed: bool = False,
) -> dict[str, Any]:
    """Export budget lines to XLSX. Returns the download URL action.

    At least one of `project_id` or `portfolio_id` is typically set; omit both
    to export everything visible to the service user.
    """
    vals: dict[str, Any] = {"include_closed": include_closed}
    if project_id is not None:
        vals["project_id"] = project_id
    if portfolio_id is not None:
        vals["portfolio_id"] = portfolio_id
    if date_from:
        vals["date_from"] = date_from
    if date_to:
        vals["date_to"] = date_to
    if category_id is not None:
        vals["category_id"] = category_id
    return _run_export_wizard("ppm.budget.export.wizard", vals)


@mcp.tool()
def ppm_export_risks(
    project_id: int | None = None,
    portfolio_id: int | None = None,
    risk_level: str | None = None,
    include_closed: bool = False,
) -> dict[str, Any]:
    """Export the risk register to XLSX.

    `risk_level` is one of 'low', 'medium', 'high', 'critical' — or omit for all.
    """
    vals: dict[str, Any] = {"include_closed": include_closed}
    if project_id is not None:
        vals["project_id"] = project_id
    if portfolio_id is not None:
        vals["portfolio_id"] = portfolio_id
    if risk_level:
        vals["risk_level"] = risk_level
    return _run_export_wizard("ppm.risk.export.wizard", vals)


@mcp.tool()
def ppm_export_resources(
    project_id: int | None = None,
    employee_id: int | None = None,
    department_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    include_cancelled: bool = False,
) -> dict[str, Any]:
    """Export resource allocations to XLSX."""
    vals: dict[str, Any] = {"include_cancelled": include_cancelled}
    if project_id is not None:
        vals["project_id"] = project_id
    if employee_id is not None:
        vals["employee_id"] = employee_id
    if department_id is not None:
        vals["department_id"] = department_id
    if date_from:
        vals["date_from"] = date_from
    if date_to:
        vals["date_to"] = date_to
    return _run_export_wizard("ppm.resource.export.wizard", vals)


# ---------------------------------------------------------------------------
# Projects from template (client card flow)
# ---------------------------------------------------------------------------


@mcp.tool()
def ppm_create_project_from_template(
    partner_id: int,
    template_id: int,
    project_name: str,
) -> dict[str, Any]:
    """Clone a project template and attach it to a customer (res.partner).

    Returns the new project id, name, portfolio_id, and program_id.
    """
    wizard_id = client().execute_kw(
        "ppm.create.project.wizard",
        "create",
        [{"partner_id": partner_id, "template_id": template_id, "project_name": project_name}],
    )
    action = client().call_action(
        "ppm.create.project.wizard", "action_create_project", [wizard_id]
    )
    project_id = action.get("res_id") if isinstance(action, dict) else None
    if not project_id:
        raise RuntimeError("Template-create wizard did not return a project id")
    return _read_state(
        "project.project",
        project_id,
        ["id", "name", "partner_id", "portfolio_id", "program_id"],
    )


# ---------------------------------------------------------------------------
# Health / introspection helpers
# ---------------------------------------------------------------------------


@mcp.tool()
def ppm_ping() -> dict[str, Any]:
    """Verify the MCP server can authenticate to Odoo and hit the PPM models.

    Returns {ok, uid, portfolios, programs, projects, risks} with counts.
    """
    c = client()
    uid = c.uid  # triggers authenticate if needed
    counts: dict[str, Any] = {"ok": True, "uid": uid}
    for model in (
        "project.portfolio",
        "project.program",
        "project.project",
        "ppm.risk",
        "ppm.change.request",
        "ppm.milestone",
        "ppm.status.report",
    ):
        try:
            counts[model] = c.execute_kw(model, "search_count", [[]])
        except Exception as e:  # noqa: BLE001
            counts[model] = f"error: {e}"
    return counts


@mcp.tool()
async def ppm_list_action_tools() -> list[dict[str, str]]:
    """List every PPM action/wizard tool this server exposes, with a one-line description.

    Useful when Claude is deciding whether to call a custom tool or fall back
    to the generic Odoo MCP's `update_record`/`search_records`.
    """
    registered = await mcp.list_tools()
    return [
        {"name": t.name, "summary": (t.description or "").strip().splitlines()[0]}
        for t in registered
    ]
