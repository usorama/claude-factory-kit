# Extend an existing upload service
The current MediaStore engine already implements upload, ownership, persistence,
and reload. Its existing upload_and_reload test passes. Do not rebuild or replace it.
R1: A user uploads a profile photo through MediaStore and still sees it after reload.
R2: A user uploads a cover photo through the SAME MediaStore and still sees it after reload.
Both features are new UI paths using an existing engine. Each is a two-hour task.
The first slice is the working profile-photo path. Record MediaStore as used by
both features, with no build of that existing capability in this change.
