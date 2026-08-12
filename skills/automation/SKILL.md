---
name: automation
description: Create and manage scheduled automations.
---

# Automation Skill

This skill provides 3 tools for creating and managing scheduled automations:
- `check_automations` - List all or inspect a specific automation
- `create_automation` - Create a new scheduled automation
- `manage_automation` - Update, pause, resume, trigger, or delete automations

You should call these tools directly instead of using ExecuteCode tool.

## Before Creating an Automation

**Always confirm with the user before calling `create_automation`.** Automations run autonomously on a schedule, so getting the details right matters. If the user's request is unclear or underspecified, ask to clarify:

- **Schedule** — "Every morning" is ambiguous. Confirm the exact time and days (e.g. "Weekdays at 9 AM in your timezone?").
- **Thread strategy** — If the task involves ongoing analysis or follow-ups, ask whether they want results in a fresh thread each time, a single persistent thread, or the current conversation.
- **Instruction** — The instruction runs without further user input. If the user gives a vague prompt like "send a weekly update", refine it: what sources? what scope? what format?
- **Delivery** — If the user hasn't mentioned how they want to receive results, ask if they want delivery (e.g. Slack) or just in-app.

Summarize what you're about to create and get a "yes" before calling the tool.

---

## Tool 1: check_automations

List all automations or inspect a specific one with execution history.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `automation_id` | str | No | Automation ID to inspect. Omit to list all. |

### Examples

```python
# List all automations
check_automations()

# Inspect a specific automation (includes last 5 executions)
check_automations(automation_id="abc-123")
```

---

## Tool 2: create_automation

Create a new scheduled automation.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | str | Yes | Short name for the automation |
| `instruction` | str | Yes | The prompt the agent will execute on each run |
| `schedule` | str | Yes | Cron expression or ISO datetime (see below) |
| `description` | str | No | Optional description |
| `thread` | str | No | `"new"` (default), `"persistent"`, or `"current"` (see Thread Strategy) |
| `delivery` | str | No | Comma-separated delivery methods (e.g. `"slack"`) |

### Thread Strategy

| Mode | Behavior |
|------|----------|
| `"new"` | Fresh thread each run — no conversation history carried over (default) |
| `"persistent"` | Single dedicated thread — all runs share conversation history |
| `"current"` | Pins to the current conversation thread — automation runs continue here |

### Schedule Format

- **Recurring (cron):** Standard 5-field cron expression
  - `0 9 * * 1-5` — weekdays at 9 AM
  - `0 */4 * * *` — every 4 hours
  - `30 8 1 * *` — 1st of each month at 8:30 AM
- **One-time (ISO datetime):**
  - `2026-03-01T10:00:00` — single execution at that time

### Examples

```python
# Daily learning digest on weekdays at 9 AM
create_automation(
    name="Morning Learning Digest",
    instruction="Summarize new assignments, upcoming deadlines, and the next recommended learning activities.",
    schedule="0 9 * * 1-5",
)

# One-time preparation reminder
create_automation(
    name="Project Preparation Reminder",
    instruction="Review the project brief and prepare a concise checklist for the presentation.",
    schedule="2026-04-30T08:00:00",
    description="Preparation checklist before the project presentation",
)

# Daily report delivered to Slack
create_automation(
    name="Daily Progress Report",
    instruction="Summarize completed work, blocked tasks, and the next planned actions.",
    schedule="0 9 * * 1-5",
    delivery="slack",
)

# Automation with persistent thread (all runs share history)
create_automation(
    name="Weekly Learning Review",
    instruction="Review the week's completed assignments and identify topics that need more practice.",
    schedule="0 9 * * 1",
    thread="persistent",
)

# Automation that continues in the current conversation
create_automation(
    name="Hourly Workspace Check",
    instruction="Summarize new workspace files and identify work that needs review.",
    schedule="0 * * * *",
    thread="current",
)
```

---

## Tool 3: manage_automation

Manage an existing automation.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `automation_id` | str | Yes | Automation ID to manage |
| `action` | str | Yes | One of: `update`, `pause`, `resume`, `trigger`, `delete` |
| `name` | str | No | New name (update only) |
| `description` | str | No | New description (update only) |
| `instruction` | str | No | New prompt (update only) |
| `schedule` | str | No | New cron or ISO datetime (update only) |
| `thread` | str | No | `"new"`, `"persistent"`, or `"current"` (update only) |
| `delivery` | str | No | Comma-separated delivery methods (update only) |
| `remove_delivery` | bool | No | Set to `true` to remove delivery config (update only) |

### Action Reference

| Action | Description |
|--------|-------------|
| `update` | Change name, description, instruction, schedule, thread strategy, or delivery |
| `pause` | Temporarily stop the automation from running |
| `resume` | Re-enable a paused automation |
| `trigger` | Run the automation immediately (outside normal schedule) |
| `delete` | Permanently remove the automation |

### Examples

```python
# Pause an automation
manage_automation(automation_id="abc-123", action="pause")

# Resume it
manage_automation(automation_id="abc-123", action="resume")

# Trigger an immediate run
manage_automation(automation_id="abc-123", action="trigger")

# Update the schedule to run every Monday at 8 AM
manage_automation(
    automation_id="abc-123",
    action="update",
    schedule="0 8 * * 1",
)

# Switch an automation to a persistent thread
manage_automation(automation_id="abc-123", action="update", thread="persistent")

# Remove delivery from an automation
manage_automation(automation_id="abc-123", action="update", remove_delivery=True)

# Delete an automation
manage_automation(automation_id="abc-123", action="delete")
```
