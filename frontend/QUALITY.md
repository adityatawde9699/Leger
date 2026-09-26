# Frontend quality strategy

Ledger is currently a JavaScript React application without a TypeScript compiler. The release baseline is explicit:

1. `npm ci` installs the locked dependency graph.
2. `npm run build` is the production compile/PWA gate and catches JSX, import, and bundling errors.
3. `npm run test:e2e` runs Chromium browser coverage for first-run setup, honest empty states, quick-capture focus/escape behavior, and command-palette focus restoration. The harness uses a same-origin mocked API and blocks service workers so failures represent UI behavior rather than a missing backend.
4. New calculation and API behavior is covered by backend tests; frontend changes must preserve documented response contracts.

Statement review, transaction correction/undo, offline queue synchronization, and mobile viewport coverage remain follow-up browser flows.
