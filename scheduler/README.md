# Local scheduler ("server" mode)

Instead of relying on GitHub Actions' `schedule:` cron (which drifts 3–15 min),
this box triggers the check at a precise wall-clock time via `workflow_dispatch`.

**Flow:** Windows Task Scheduler → `trigger-permit-check.ps1` → `gh workflow run
permit-check.yml` → GitHub spins a runner (~30–50s) → `check_permits.py` runs.

So a 7:00:00 dispatch puts the recreation.gov request out somewhere around
7:00:35–7:00:55. There's no way to remove the runner-startup latency from the
GitHub side; if you need tighter than that, the check has to run locally.

## One-time setup

1. **Install + confirm GitHub CLI** (already installed here): `gh --version`

2. **Create a token.** GitHub → Settings → Developer settings → Fine-grained
   personal access tokens. Repository access: `JeffreyMichel/trailgate` only.
   Permissions: **Actions → Read and write**. Copy the token.

3. **Give the token to the script** (pick one):
   - Save it to `scheduler/gh_token.txt` (git-ignored), or
   - Set a user env var: `setx GH_TOKEN "github_pat_..."`

4. **Verify the workflow is on `main`.** `workflow_dispatch` only sees workflow
   files that exist on the default branch:
   ```
   git add .github/workflows/permit-check.yml scheduler .gitignore
   git commit -m "Add local scheduler + slim permit-check workflow"
   git push
   ```

5. **Test the trigger by hand:**
   ```
   powershell -ExecutionPolicy Bypass -File .\scheduler\trigger-permit-check.ps1
   gh run list -R JeffreyMichel/trailgate --workflow permit-check.yml
   ```

6. **Register the scheduled task** (elevated PowerShell):
   ```
   powershell -ExecutionPolicy Bypass -File .\scheduler\Register-Task.ps1
   ```

7. **Dry-run the task:**
   ```
   Start-ScheduledTask -TaskName "Trailgate Permit Check"
   Get-Content .\scheduler\logs\trigger-*.log -Tail 5
   ```

## Changing the time

Edit `$RunAt` in `Register-Task.ps1` and re-run it, or use Task Scheduler's GUI
(`taskschd.msc` → "Trailgate Permit Check").

## Notes

- The task uses `S4U` logon: runs whether or not you're logged in, no stored
  password. `WakeToRun` wakes the machine from sleep; it won't fire if the box
  is fully powered off (`StartWhenAvailable` makes it catch up late, harmlessly).
- `check.yml` is unchanged — still runs CI on push and keeps its own `schedule:`
  cron as an unreliable backup. Remove that cron block if the double runs bother
  you.
- Logs rotate monthly in `scheduler/logs/`.
