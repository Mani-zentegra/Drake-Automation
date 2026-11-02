# Zoho Creator Form Automation Rules

## 1. Zero-Snapshot Execution Principle
- Avoid taking full accessibility/DOM snapshots repeatedly during form entry.
- Direct-target verified selectors via batch filling or DOM evaluation to cut execution latency by >85%.

## 2. Dynamic Subform Grid Mechanics
- **Virtual DOM / Offscreen Elements**: Zoho Creator subforms may keep newly added rows unrendered until scrolled into view.
- **Event Dispatching**: When setting values directly, always dispatch:
  1. `input` (bubbles: true)
  2. `change` (bubbles: true)
  3. `blur` (bubbles: true)
  This ensures Zoho Creator client-side state models recognize the changes.

## 3. Date & Value Formats
- **Date of Birth**: Must conform to Zoho Creator's date-time format: `dd-MMM-yyyy HH:mm:ss` (e.g. `10-Apr-2015 00:00:00` or `10-Apr-2015`).
- **Months in Home**: Integer string (typically `12`).
- **Relationship**: Case-matching options (`Son`, `Daughter`, `Child`, `Father`, `Mother`, `Other`).

## 4. Safety Guardrails
- **NEVER submit automatically**: Form submissions alter production database records in Zoho Creator and trigger downstream Webhooks/Deluge workflows.
- Hold state on completion and emit execution metrics (duration in ms, row count, verification status).
