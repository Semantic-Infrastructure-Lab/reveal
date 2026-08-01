## TASK-1: Fix the login timeout bug
```yaml
status: open
priority: high
```
Users are getting logged out after 5 minutes of inactivity instead of the
configured 30. Looks like the session refresh isn't firing on API calls made
from the background sync worker.

## TASK-2: Add dark mode toggle
```yaml
status: open
priority: medium
```
Design has the mockups ready. Needs a persisted user preference and a CSS
variable swap, no new dependencies.

## TASK-3: Migrate build to the new CI runner
```yaml
status: done
priority: low
```
Moved from the legacy self-hosted runner to the managed one. Build time
dropped from 11m to 4m.
