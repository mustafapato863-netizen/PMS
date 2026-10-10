# Basis test CI isolation

Two basis-comparison test modules cleared the runner's `CI` at import, affecting unrelated sibling tests. Removed only those two statements; no business assertion, tolerance, skip rule, source workbook or scoring code changed. A portable two-case regression reloads both modules and checks the runner policy remains `true`.

Independent focused existing modules plus Marketing:53passed/1existing CI skip,3.42seconds. Regression plus basis modules:31passed,1.80seconds. Complete anonymous CI repeat:1414passed/2existing skips/486warnings,208.84seconds (before the two new regression cases were added to full collection). Existing intended Marketing CI skip remains unchanged; the private workbook's131-versus68 local UAT failure remains separately recorded, not reconciled by this fix. The other existing skip is unchanged.

Artifacts: `D:/Projects/PMS_Dashboard/tmp/reviewer-ci-isolation-{focused,regression,full}-20261010.xml`. This is test-environment hygiene, not additional scoring admission or production acceptance.
