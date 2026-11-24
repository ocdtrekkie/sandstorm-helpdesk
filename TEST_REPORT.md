# Validation report

## Executed in the generation environment

- Core unittest suite: **44 passed**.
- Flask integration suite: **17 skipped**, because Flask is not installed in this environment.
- Overall runner: 61 discovered, 44 passed, 17 skipped, no failures or errors.
- All Python source files parsed successfully with Python's AST parser.
- All seven Jinja template files loaded and rendered with representative SQLite-backed data and StrictUndefined.
- The exact SQLite escaped-LIKE search expression was exercised with percent, underscore, backslash, subject, and ticket-number inputs.
- The backup helper created a consistent snapshot, passed SQLite integrity checking, and preserved an image attachment.
- The Sandstorm configuration helper generated a definition using a temporary dummy app ID; that generated file was removed and is not shipped.
- The ZIP archive was checked for integrity and expected source files.

## Not validated here

- Flask/Waitress startup, HTTP requests, cookies, and the 17 included web integration tests.
- Browser interaction, CSS layout, file uploads through a real browser, and Sandstorm iframe integration.
- Cap'n Proto package-definition compilation, SDK file tracing, signed SPK generation, or installation on a Sandstorm host.
- Dependency resolution/auditing in the target operating system.

The source is implemented, but this report is not a claim of a fully runtime-tested or production-certified deployment.
Install requirements and run the entire suite without skips, then perform the Sandstorm acceptance checklist in README.md.

## Core test output

```text
test_admin_can_close (tests.test_core.CoreTests.test_admin_can_close) ... ok
test_admin_can_create_taxonomy (tests.test_core.CoreTests.test_admin_can_create_taxonomy) ... ok
test_all_roles_create_owned_tickets (tests.test_core.CoreTests.test_all_roles_create_owned_tickets) ... ok
test_anonymous_or_permissionless_cannot_create (tests.test_core.CoreTests.test_anonymous_or_permissionless_cannot_create) ... ok
test_attachment_cannot_reference_another_tickets_comment (tests.test_core.CoreTests.test_attachment_cannot_reference_another_tickets_comment) ... ok
test_case_insensitive_unique_names (tests.test_core.CoreTests.test_case_insensitive_unique_names) ... ok
test_close_already_closed_conflict (tests.test_core.CoreTests.test_close_already_closed_conflict) ... ok
test_closed_ticket_blocks_comments_for_every_role (tests.test_core.CoreTests.test_closed_ticket_blocks_comments_for_every_role) ... ok
test_default_reopen_disabled (tests.test_core.CoreTests.test_default_reopen_disabled) ... ok
test_display_name_does_not_grant_ownership (tests.test_core.CoreTests.test_display_name_does_not_grant_ownership) ... ok
test_empty_comment_rejected (tests.test_core.CoreTests.test_empty_comment_rejected) ... ok
test_image_name_and_content_are_safely_normalized (tests.test_core.CoreTests.test_image_name_and_content_are_safely_normalized) ... ok
test_image_validation_and_limits (tests.test_core.CoreTests.test_image_validation_and_limits) ... ok
test_inactive_historical_option_retained (tests.test_core.CoreTests.test_inactive_historical_option_retained) ... ok
test_inactive_option_cannot_be_newly_selected (tests.test_core.CoreTests.test_inactive_option_cannot_be_newly_selected) ... ok
test_initialization_is_idempotent (tests.test_core.CoreTests.test_initialization_is_idempotent) ... ok
test_invalid_image_leaves_no_ticket (tests.test_core.CoreTests.test_invalid_image_leaves_no_ticket) ... ok
test_invalid_status_rejected (tests.test_core.CoreTests.test_invalid_status_rejected) ... ok
test_last_active_option_cannot_be_disabled (tests.test_core.CoreTests.test_last_active_option_cannot_be_disabled) ... ok
test_markdown_formatting (tests.test_core.CoreTests.test_markdown_formatting) ... ok
test_markdown_rejects_xss_and_remote_images (tests.test_core.CoreTests.test_markdown_rejects_xss_and_remote_images) ... ok
test_missing_ticket (tests.test_core.CoreTests.test_missing_ticket) ... ok
test_nonadmins_cannot_change_policy (tests.test_core.CoreTests.test_nonadmins_cannot_change_policy) ... ok
test_nonadmins_cannot_manage_taxonomy (tests.test_core.CoreTests.test_nonadmins_cannot_manage_taxonomy) ... ok
test_only_staff_change_classification (tests.test_core.CoreTests.test_only_staff_change_classification) ... ok
test_only_staff_close (tests.test_core.CoreTests.test_only_staff_close) ... ok
test_original_ticket_images (tests.test_core.CoreTests.test_original_ticket_images) ... ok
test_other_requester_cannot_comment (tests.test_core.CoreTests.test_other_requester_cannot_comment) ... ok
test_other_requester_cannot_reopen_even_when_enabled (tests.test_core.CoreTests.test_other_requester_cannot_reopen_even_when_enabled) ... ok
test_owner_can_add_image_without_text (tests.test_core.CoreTests.test_owner_can_add_image_without_text) ... ok
test_owner_can_comment_with_image (tests.test_core.CoreTests.test_owner_can_comment_with_image) ... ok
test_owner_reopen_enabled_and_closure_cleared (tests.test_core.CoreTests.test_owner_reopen_enabled_and_closure_cleared) ... ok
test_policy_changes_are_audited (tests.test_core.CoreTests.test_policy_changes_are_audited) ... ok
test_policy_revocation_immediate (tests.test_core.CoreTests.test_policy_revocation_immediate) ... ok
test_repeated_status_cycles_record_history (tests.test_core.CoreTests.test_repeated_status_cycles_record_history) ... ok
test_requester_own_only (tests.test_core.CoreTests.test_requester_own_only) ... ok
test_sql_text_not_executable (tests.test_core.CoreTests.test_sql_text_not_executable) ... ok
test_staff_always_reopen (tests.test_core.CoreTests.test_staff_always_reopen) ... ok
test_staff_visibility (tests.test_core.CoreTests.test_staff_visibility) ... ok
test_supervisor_comments_on_own_only (tests.test_core.CoreTests.test_supervisor_comments_on_own_only) ... ok
test_supervisor_reopens_own_only_when_enabled (tests.test_core.CoreTests.test_supervisor_reopens_own_only_when_enabled) ... ok
test_technician_and_admin_can_comment_on_any_open (tests.test_core.CoreTests.test_technician_and_admin_can_comment_on_any_open) ... ok
test_ticket_validation (tests.test_core.CoreTests.test_ticket_validation) ... ok
test_transaction_failure_rolls_back (tests.test_core.CoreTests.test_transaction_failure_rolls_back) ... ok
test_admin_and_form_pages_render (tests.test_web.WebTests.test_admin_and_form_pages_render) ... skipped 'Flask is not installed in this environment'
test_attachment_enforces_parent_visibility (tests.test_web.WebTests.test_attachment_enforces_parent_visibility) ... skipped 'Flask is not installed in this environment'
test_comment_image_through_form (tests.test_web.WebTests.test_comment_image_through_form) ... skipped 'Flask is not installed in this environment'
test_create_ticket_through_form (tests.test_web.WebTests.test_create_ticket_through_form) ... skipped 'Flask is not installed in this environment'
test_csrf_required (tests.test_web.WebTests.test_csrf_required) ... skipped 'Flask is not installed in this environment'
test_development_identity_ignores_spoofed_headers (tests.test_web.WebTests.test_development_identity_ignores_spoofed_headers) ... skipped 'Flask is not installed in this environment'
test_identity_required (tests.test_web.WebTests.test_identity_required) ... skipped 'Flask is not installed in this environment'
test_new_ticket_validation_retains_text (tests.test_web.WebTests.test_new_ticket_validation_retains_text) ... skipped 'Flask is not installed in this environment'
test_nonadmin_settings_blocked (tests.test_web.WebTests.test_nonadmin_settings_blocked) ... skipped 'Flask is not installed in this environment'
test_owner_status_workflow (tests.test_web.WebTests.test_owner_status_workflow) ... skipped 'Flask is not installed in this environment'
test_preview_is_sanitized (tests.test_web.WebTests.test_preview_is_sanitized) ... skipped 'Flask is not installed in this environment'
test_requester_all_view_blocked (tests.test_web.WebTests.test_requester_all_view_blocked) ... skipped 'Flask is not installed in this environment'
test_requester_direct_ticket_access (tests.test_web.WebTests.test_requester_direct_ticket_access) ... skipped 'Flask is not installed in this environment'
test_search_special_characters_and_filters (tests.test_web.WebTests.test_search_special_characters_and_filters) ... skipped 'Flask is not installed in this environment'
test_secure_cookies_default_in_production (tests.test_web.WebTests.test_secure_cookies_default_in_production) ... skipped 'Flask is not installed in this environment'
test_security_headers (tests.test_web.WebTests.test_security_headers) ... skipped 'Flask is not installed in this environment'
test_supervisor_reads_but_cannot_write_other_ticket (tests.test_web.WebTests.test_supervisor_reads_but_cannot_write_other_ticket) ... skipped 'Flask is not installed in this environment'

----------------------------------------------------------------------
Ran 61 tests in 0.326s

OK (skipped=17)
```
