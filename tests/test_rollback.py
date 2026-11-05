import json
from pathlib import Path
import subprocess

import pytest
from tools.rollback import RecoveryError, apply, fetch, git, preview


@pytest.fixture
def repository(tmp_path):
    remote = tmp_path / 'remote.git'
    root = tmp_path / 'working'
    subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
    subprocess.run(['git', 'init', '-b', 'main', str(root)], check=True, capture_output=True)
    git(root, 'config', 'user.name', 'Synthetic Release Test')
    git(root, 'config', 'user.email', 'synthetic@example.com')
    git(root, 'remote', 'add', 'origin', str(remote))
    (root / 'app.py').write_text("print('old')\n")
    (root / 'deployments.json').write_text(json.dumps({'production1': {'branch': 'main', 'entry': 'app.py'}}))
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'Old stable release')
    old = git(root, 'rev-parse', 'HEAD')
    git(root, 'tag', 'release/production1/v1', old)
    (root / 'app.py').write_text("print('new')\n")
    (root / 'tools').mkdir()
    (root / 'tools/rollback.py').write_text('# preserve modern recovery controls\n')
    (root / 'RELEASES.md').write_text('Current recovery instructions\n')
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'Current release')
    head = git(root, 'rev-parse', 'HEAD')
    git(root, 'push', 'origin', 'main', '--tags')
    fetch(root)
    return root, remote, old, head


def test_preview_never_changes_remote_or_local_files(repository):
    root, remote, old, head = repository
    plan = preview(root, 'production1', 'v1')
    assert plan['head'] == head and plan['source'] == old and plan['changed_files'] == ['app.py']
    assert git(remote, 'rev-parse', 'main') == head
    assert 'new' in (root / 'app.py').read_text()


def test_restore_is_fast_forward_keeps_controls_and_dirty_files_and_can_undo_itself(repository):
    root, remote, old, head = repository
    (root / 'app.py').write_text('uncommitted user work\n')
    (root / 'private-untracked.txt').write_text('synthetic private data\n')
    plan = preview(root, 'production1', 'v1')
    checked = []
    def validate(tree):
        assert 'old' in (tree / 'app.py').read_text()
        assert 'modern recovery' in (tree / 'tools/rollback.py').read_text()
        checked.append(True)
    result = apply(root, plan, expected_head=head, confirm_site='production1', validator=validate)
    assert checked and result['status'] == 'published'
    restored = git(remote, 'rev-parse', 'main')
    assert git(remote, 'rev-parse', restored + '^') == head
    assert git(remote, 'show', restored + ':app.py') == "print('old')"
    assert git(remote, 'rev-parse', result['backup']) == head
    assert (root / 'app.py').read_text() == 'uncommitted user work\n'
    assert (root / 'private-untracked.txt').exists()
    fetch(root)
    undo = preview(root, 'production1', result['backup'])
    undone = apply(root, undo, expected_head=restored, confirm_site='production1', validator=lambda tree: None)
    assert git(remote, 'show', undone['commit'] + ':app.py') == "print('new')"


def test_failed_target_checks_publish_nothing(repository):
    root, remote, old, head = repository
    def fail(tree):
        raise RecoveryError('synthetic target test failure')
    with pytest.raises(RecoveryError):
        apply(root, preview(root, 'production1', 'v1'), expected_head=head, confirm_site='production1', validator=fail)
    assert git(remote, 'rev-parse', 'main') == head
    assert git(remote, 'tag', '--list', 'rollback-backup/*') == ''


def test_wrong_site_confirmation_and_stale_preview_do_not_publish(repository):
    root, remote, old, head = repository
    plan = preview(root, 'production1', 'v1')
    with pytest.raises(RecoveryError, match='確認站台'):
        apply(root, plan, expected_head=head, confirm_site='production2', validator=lambda tree: None)
    (root / 'app.py').write_text("print('concurrent new release')\n")
    git(root, 'add', 'app.py'); git(root, 'commit', '-m', 'Concurrent release'); git(root, 'push', 'origin', 'main')
    current = git(remote, 'rev-parse', 'main')
    with pytest.raises(RecoveryError, match='重新預覽'):
        apply(root, plan, expected_head=head, confirm_site='production1', validator=lambda tree: None)
    assert git(remote, 'rev-parse', 'main') == current


def test_concurrent_push_during_checks_is_rejected_atomically(repository):
    root, remote, old, head = repository
    current = []
    def concurrent_release(tree):
        (root / 'app.py').write_text("print('another release during tests')\n")
        git(root, 'add', 'app.py'); git(root, 'commit', '-m', 'Publish while recovery checks run')
        git(root, 'push', 'origin', 'main')
        current.append(git(remote, 'rev-parse', 'main'))
    with pytest.raises(RecoveryError):
        apply(root, preview(root, 'production1', 'v1'), expected_head=head, confirm_site='production1', validator=concurrent_release)
    assert git(remote, 'rev-parse', 'main') == current[0]
    assert git(remote, 'tag', '--list', 'rollback-backup/*') == ''


@pytest.mark.parametrize('version', ['main', 'release/production2/v1', 'v1^{tree}', '../v1'])
def test_arbitrary_revisions_and_other_site_tags_are_rejected(repository, version):
    root, remote, old, head = repository
    with pytest.raises(RecoveryError):
        preview(root, 'production1', version)
    assert git(remote, 'rev-parse', 'main') == head
