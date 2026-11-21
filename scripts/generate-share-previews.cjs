'use strict';

// Compatibility entry point for the original preview command. The Python
// builder validates every graph and maintains both current and legacy links.
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const result = spawnSync(process.env.SHARING_PYTHON || 'python3', [
  path.join(__dirname, 'build_share_pages.py'), ...process.argv.slice(2)
], { cwd: root, stdio: 'inherit' });
if (result.error) {
  process.stderr.write(result.error.message + '\n');
  process.exitCode = 1;
} else {
  process.exitCode = result.status === null ? 1 : result.status;
}
