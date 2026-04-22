# qod-ppm-odoo-mcp

MCP server for the [QOD PPM](https://CenterQOD.com) Odoo plugin.

Exposes the plugin's **buttons, wizards, and workflow transitions** as MCP
tools — the things a generic Odoo CRUD server can't express.

## Design

This server is intentionally **thin**. It does not reimplement Odoo CRUD.
Run it alongside a generic Odoo MCP (e.g.
[`ivnvxd/mcp-server-odoo`](https://github.com/ivnvxd/mcp-server-odoo)):

| Need                                                         | Use                                           |
|--------------------------------------------------------------|-----------------------------------------------|
| Create/read/update/delete portfolios, programs, projects, tasks, risks, ... | Generic Odoo MCP (`create_record`, `search_records`, ...) |
| Transition workflow state (submit, approve, achieve, close, ...) | **This server**                               |
| Run a wizard (status report, CR reject, budget export, ...)   | **This server**                               |
| Domain rules (P×I matrix move with validation, ...)          | **This server**                               |

Put simply: **if there's a button in the Odoo UI that does something
non-trivial when clicked, it's a tool here.** CRUD wraps fields; this wraps
buttons.

## Install

```bash
pip install qod-ppm-odoo-mcp
```

Or from source:

```bash
git clone https://github.com/wethti/qod-ppm-odoo-mcp
cd qod-ppm-odoo-mcp
pip install -e .
```

## Configure

Create a service user in Odoo and give it the PPM groups you need
(`group_ppm_admin` or scoped alternatives). Generate an API key from the
user's preferences page. Then set:

```bash
export ODOO_URL="https://your-odoo.example.com"
export ODOO_DB="your_db_name"
export ODOO_USERNAME="ppm-service@example.com"
export ODOO_API_KEY="…"   # preferred
# or ODOO_PASSWORD="…"
```

A [`.env.example`](.env.example) is included.

## Run

**stdio (default)** — for Claude Desktop / Claude Code / anything that spawns
an MCP server as a subprocess:

```bash
qod-ppm-mcp
```

**Streamable HTTP** — for remote access (another VPS, an agent host, etc.):

```bash
export QOD_PPM_MCP_TRANSPORT=http
export QOD_PPM_MCP_HOST=0.0.0.0
export QOD_PPM_MCP_PORT=8765
qod-ppm-mcp
```

Put a reverse proxy with TLS + auth in front if exposed to the internet.

## Claude Code / Claude Desktop config

Add to `~/.claude.json` (Claude Code) or `claude_desktop_config.json`:

```jsonc
{
  "mcpServers": {
    "qod-ppm": {
      "command": "qod-ppm-mcp",
      "env": {
        "ODOO_URL": "https://your-odoo.example.com",
        "ODOO_DB": "your_db_name",
        "ODOO_USERNAME": "ppm-service@example.com",
        "ODOO_API_KEY": "…"
      }
    },
    "odoo": {
      "command": "uvx",
      "args": ["mcp-server-odoo"],
      "env": {
        "ODOO_URL": "https://your-odoo.example.com",
        "ODOO_DB": "your_db_name",
        "ODOO_USERNAME": "ppm-service@example.com",
        "ODOO_API_KEY": "…"
      }
    }
  }
}
```

Both servers point to the same Odoo. Claude sees tools namespaced as
`mcp__qod-ppm__*` (workflow actions) and `mcp__odoo__*` (generic CRUD).

## Tool reference

Call `ppm_list_action_tools` to get the current list at runtime. Groups:

### Milestones (`ppm.milestone`)
- `ppm_milestone_start` / `achieve` / `miss` / `cancel` / `reopen`

### Status Reports (`ppm.status.report` + wizard)
- `ppm_status_report_generate(project_id, period?, commentary?)`
  — runs the wizard, auto-fills RAG/budget/risks/milestones, creates report
- `ppm_status_report_publish(report_id)`
- `ppm_status_report_reset_draft(report_id)`
- `ppm_status_report_print_url(report_id)` — returns the PDF action

### Change Requests (`ppm.change.request` + reject wizard)
- `ppm_change_request_submit` / `start_review` / `approve` / `reset_draft`
- `ppm_change_request_reject(cr_id, reason)` — runs the reject wizard

### Risks (`ppm.risk`)
- Workflow: `ppm_risk_start_analysis` / `start_mitigation` / `start_monitoring` /
  `mark_occurred` / `close` / `reopen`
- `ppm_risk_move_in_matrix(risk_id, probability, impact)` — probability and
  impact are integers 1–5; server recomputes score and level

### Issues (risks flagged as issue_type)
- `ppm_issue_assign` / `start` / `resolve` / `escalate`

### Role Assignments (`ppm.role.assignment`)
- `ppm_role_activate` / `approve_and_activate` / `revoke` / `reset_draft`
  (each syncs the Odoo security group)

### Exports (wizards → XLSX)
- `ppm_export_budget(project_id?, portfolio_id?, date_from?, date_to?, category_id?, include_closed?)`
- `ppm_export_risks(project_id?, portfolio_id?, risk_level?, include_closed?)`
- `ppm_export_resources(project_id?, employee_id?, department_id?, date_from?, date_to?, include_cancelled?)`

All three return an `ir.actions.act_url` pointing at `/web/content/<id>?download=true`.

### Client Card Projects
- `ppm_create_project_from_template(partner_id, template_id, project_name)`

### Introspection
- `ppm_ping()` — auth + basic counts
- `ppm_list_action_tools()` — self-describing tool list

## Compatibility

- Odoo 18.0 Community / Enterprise
- QOD PPM modules: `qod_ppm_core`, `qod_ppm_budget`, `qod_ppm_change_request`,
  `qod_ppm_client_card_projects`, `qod_ppm_dashboard`, `qod_ppm_resource`,
  `qod_ppm_risk`, `qod_ppm_roles`, `qod_ppm_roles_crm`, `qod_ppm_roles_mrp`,
  `qod_ppm_scoring`, `qod_ppm_status`, `qod_ppm_task_status`

## License

LGPL-3.0-or-later — matching the QOD PPM modules.
