---
name: zoho-fast-automation
description: High-performance, zero-overhead browser automation for Zoho Creator forms using existing Playwright MCP session and verified selectors.
---

# Zoho Fast Automation Skill

Enables instant, batch automated entry into **Zoho Creator** forms (such as `Dependents`) by eliminating repeated DOM accessibility snapshots, reusing pre-verified selectors, and leveraging the existing authenticated browser profile.

## Browser Session Profile
* **Profile Path**: `C:\Users\ADMIN\AppData\Local\DrakeZohoPlaywrightProfile`
* **Target Form URL**: `https://creatorapp.zoho.in/zentegraindia/drake-automation/#Form:Dependents`
* **Authentication**: Reuses the user's existing logged-in session.

## Performance Optimizations
1. **Zero-Snapshot Execution**: Eliminates the 30-second DOM snapshot loop by directly targeting verified selectors.
2. **Batched Execution**: Dispatches input events to all subform cells in a single call via `browser_evaluate` or `browser_fill_form`.
3. **Dynamic Row Handling**: Automatically supports single or multi-row dependents.
4. **Execution Metrics**: Measures exact execution latency (`durationMs`) and row counts.
5. **Safe Mode**: Pre-populates all data and verifies fields, but **never clicks Submit**.

## Quick Execution Workflow

### Option A: Using Playwright MCP in Antigravity
Call `browser_evaluate` with the packaged runner in `scripts/fill_dependents.js`:

```json
{
  "ServerName": "playwright",
  "ToolName": "browser_evaluate",
  "Arguments": {
    "function": "() => { ... }"
  }
}
```

### Option B: Standalone Runner
Run the verified Node/Python script directly with your existing persistent profile:
```powershell
node .agents/skills/zoho-fast-automation/scripts/fill_dependents.js
```

## References
* Verified Selectors: [selectors.md](file:///c:/Users/ADMIN/Desktop/Drake%20Automation/.agents/skills/zoho-fast-automation/references/selectors.md)
* Zoho Form Rules: [zoho-form-rules.md](file:///c:/Users/ADMIN/Desktop/Drake%20Automation/.agents/skills/zoho-fast-automation/references/zoho-form-rules.md)
* Sample Payloads: [dependents.json](file:///c:/Users/ADMIN/Desktop/Drake%20Automation/.agents/skills/zoho-fast-automation/examples/dependents.json)
