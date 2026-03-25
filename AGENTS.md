# AGENTS.md

## Workflow Mode (Mandatory)
- Use **direct-main style** by default.
- Do **not** create PRs, PR descriptions, or call any PR/make_pr tools unless explicitly asked by the user.
- Commit changes directly to `main` branch with clear commit messages.
- If no file changes are made, do not create empty commits.

## Execution Style
- First inspect and explain approach briefly.
- Then implement in small, safe commits.
- Avoid unnecessary refactors unless requested.
- Preserve existing behavior unless change request says otherwise.

## Output Format
Final response must contain:
1. What changed (concise bullet list)
2. Files touched
3. Commands run (with pass/fail note)
4. Any risks or follow-up items (only if needed)

## Testing Rules
- Run only relevant checks/tests.
- If tests are skipped, explicitly state why.
- Do not claim success without command output.

## Safety / Guardrails
- Do not add fake UI workflows or placeholder screens that are not backed by real APIs/actions.
- For admin features, every UI action must map to a real backend workflow.
- Keep chatbot answers grounded to approved documents only, unless user explicitly requests otherwise.

## Planning Requests
- If user asks for planning/analysis phase, do not perform major refactors.
- Only add planning docs and minimal diagnostics unless explicitly approved for implementation.

## Override Rule
- User instruction in current chat always overrides this file.