# VERIFICATION.md

## Purpose

Define verification expectations for 06_Stock baseline automation.

## Standard Local Verification

For behavior changes, run from the repository root unless noted otherwise:

```powershell
cd 70_Imports\scripts
python -m pytest
cd ..\..
python scripts\quality_gate.py
git diff --check
git status --short --branch
```

The quality gate runs the import pipeline against the repository baseline,
executes pytest, checks raw immutability, checks generated Markdown outside-block
preservation, validates processed output contracts, and scans generated Markdown
AUTO-GENERATED blocks for sensitive-pattern candidates.

## Docs-Only Verification

For a scoped docs-only contract change, the minimum acceptable verification is:

```powershell
git status --short --branch
git diff --check
```

Then review changed files against:

- `PROJECT_BOUNDARY.md`
- `DATA_SCOPE.md`
- `SAFETY_POLICY.md`
- `APPROVALS.md`

If tests or the quality gate are not run for docs-only work, report them as
`NOT RUN` with a reason. Do not imply they passed.

## Live-Vault Dry-Run Verification

Before any actual live-vault write:

1. Verify the baseline repository first.
2. Run the import entrypoint with `--dry-run`.
3. Write dry-run evidence outside this repository, outside the live vault, and
   outside Google Drive synced folders.
4. Review expected file changes.
5. Confirm no private raw values are copied into closeout.

Dry-run evidence is a precondition for actual live writes. It is not itself
approval for the write.

## Actual Live Write Verification

Actual live writes require matching evidence and all live-write confirmation
flags enforced by `70_Imports/scripts/main.py`.

Closeout must report:

- baseline verification result;
- dry-run evidence path class, not private contents;
- expected changes reviewed;
- actual live-write command status;
- changed live-vault path summary;
- safety checks;
- risks and assumptions.

## NOT RUN Principle

If a check was not executed, mark it `NOT RUN` and explain why. Do not mark
unrun checks as passing.

## Safety Pattern Interpretation

Policy wording such as `password`, `token`, `account`, `broker`, or `API key`
inside safety rules is not automatically a secret leak. A private value or
assignment is the stop condition. Report possible private values without
printing them.
