# Frontend quality strategy

Ledger is currently a JavaScript React application without a TypeScript compiler or browser-test runner. The release baseline is explicit:

1. `npm ci` installs the locked dependency graph.
2. `npm run build` is the production compile/PWA gate and catches JSX, import, and bundling errors.
3. Reviewers use the release checklist for keyboard, mobile, empty-state, loading, error, and reduced-motion smoke checks.
4. New calculation and API behavior is covered by backend tests; frontend changes must preserve documented response contracts.

The next frontend quality investment is a browser test runner with focused flows for first-run setup, statement review, transaction correction/undo, and keyboard dialog behavior. This remains Phase 2 work rather than being implied by a production build.
