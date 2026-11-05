// npm task bridge for the existing Python/Streamlit application.
import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
const local = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python';
const python = process.env.PYTHON_EXECUTABLE || (existsSync(local) ? local : 'python3');
const task = process.argv[2];
function run(args) {
  const result = spawnSync(python, args, { stdio: 'inherit', env: process.env });
  if (result.error) { console.error('Cannot start Python; create .venv and install requirements.txt.'); process.exit(1); }
  if (result.status !== 0) process.exit(result.status || 1);
}
if (task === 'build') {
  run(['-m', 'compileall', '-q', 'app.py', 'staging_app.py', 'limited_app.py', 'limited_ui.py', 'limited_report.py', 'approval_app.py', 'approval_ui.py', 'app_ui.py', 'display_tables.py', 'access.py', 'authentication.py', 'approvals.py', 'google_access.py', 'runtime_database.py', 'member_commission.py', 'settlement.py', 'report_validation.py', 'mobile_upload.py', 'tools']);
  run(['-m', 'pytest', '-q']);
  console.log('BUILD PASSED: Python compilation and application test suite.');
} else if (task === 'start') {
  run(['-m', 'streamlit', 'run', 'staging_app.py', '--server.address', '0.0.0.0', '--server.headless', 'true', '--browser.gatherUsageStats', 'false', ...process.argv.slice(3)]);
} else if (task === 'test') run(['-m', 'pytest', '-q', ...process.argv.slice(3)]);
else if (task === 'db:init') run(['tools/init_approval_db.py']);
else if (task === 'db:check') run(['tools/check_neon_db.py']);
else { console.error('Unknown task'); process.exit(1); }
