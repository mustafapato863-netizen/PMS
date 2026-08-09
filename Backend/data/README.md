# Runtime Data Directory

This directory is runtime-only storage for transitional JSON repositories and local upload assets.

- Do not commit employee, performance, action, user, upload, or note data.
- Production data must be stored in the database or an approved private persistent volume.
- The JSON files in this directory are ignored by Git and must never be used as fixtures.
- Use synthetic data under `tests/fixtures` for automated tests.

The relational database is the target source of truth. JSON compatibility paths will be removed after the database cutover is verified.
