# Fix one authorization bypass
R1: A child must not read another family's report through GET /reports/:id.
Use the existing identity resolver. The endpoint must return 403 and no report
body for the other family, while the own-family request returns 200 with its report.
The named test is test_cross_family_report_denied. Run the green control, then
sabotage by removing the family ownership predicate. That named test must fail.
Restore the predicate and the named test must pass again. Record all exit codes.
This is one three-hour slice through route, authorization, and response layers.
Do not build a new security framework or change unrelated endpoints.
