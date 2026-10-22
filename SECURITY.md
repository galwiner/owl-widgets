# Security policy

## Supported versions

OWL is currently in its `0.x` development series. Security fixes are applied to the latest release only; users should upgrade to the newest published version before reporting or reproducing an issue.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Report it privately through [GitHub's private vulnerability reporting](https://github.com/galwiner/owl-widgets/security/advisories/new).

Include, when possible:

- the affected OWL and Python versions;
- the notebook host and browser;
- steps or a minimal notebook that reproduces the issue;
- the potential impact; and
- any suggested mitigation.

You should receive an acknowledgment within seven days. After the report is validated, fixes and disclosure timing will be coordinated with the reporter. If private vulnerability reporting is unavailable, contact the repository owner through their GitHub profile without including sensitive details publicly.

## Scope

OWL performs numerical optics calculations in Python and renders notebook widgets with bundled JavaScript. Released widgets are designed to work offline and do not intentionally send notebook data to external services. Reports involving unsafe rendering, dependency vulnerabilities, package integrity, or unintended data exposure are in scope.
