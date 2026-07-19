import test from 'node:test';
import assert from 'node:assert/strict';
import { buildApiUrl, normalizeApiBase } from './api-url.mjs';

test('normalizeApiBase trims trailing slashes', () => {
  assert.equal(normalizeApiBase('https://leger-node.onrender.com/'), 'https://leger-node.onrender.com');
  assert.equal(normalizeApiBase('https://leger-node.onrender.com'), 'https://leger-node.onrender.com');
});

test('buildApiUrl joins base and path without duplicate slashes', () => {
  assert.equal(buildApiUrl('/ping', 'https://leger-node.onrender.com/'), 'https://leger-node.onrender.com/ping');
  assert.equal(buildApiUrl('/profile', 'https://leger-node.onrender.com'), 'https://leger-node.onrender.com/profile');
  assert.equal(buildApiUrl('/analytics/forecast', 'http://localhost:8000/'), 'http://localhost:8000/analytics/forecast');
});
