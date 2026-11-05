"""Repository-owner recovery CLI. Never accepts app users' input or force-pushes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
CONTROL_FILES = ('tools/rollback.py', 'deployments.json', 'RELEASES.md', 'AGENTS.md',
                 '.github/workflows/rollback.yml', '.github/workflows/tests.yml')


class RecoveryError(Exception):
    pass


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], text=True, capture_output=True)
    if result.returncode:
        raise RecoveryError(f'Git 操作失敗（{args[0]}）；請檢查權限、分支保護或遠端是否已有新提交。')
    return result.stdout.strip()


def sites(root=ROOT):
    return json.loads((root / 'deployments.json').read_text())


def fetch(root):
    git(root, 'fetch', 'origin', '--prune', '--tags')


def snapshot(root, site, version):
    prefixes = (f'release/{site}/', f'rollback-backup/{site}/')
    if '/' in version and not version.startswith(prefixes):
        raise RecoveryError('只能選擇該站自己的版本標籤，不能使用其他站台的版本。')
    tag = version if version.startswith(prefixes) else f'release/{site}/{version}'
    if not tag.startswith(prefixes) or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/._-' for c in tag):
        raise RecoveryError('版本名稱不合法，請選擇該站自己的 release 或 rollback-backup 標籤。')
    # --verify resolves a literal, site-scoped tag; revisions and arbitrary branches are not accepted.
    return git(root, 'rev-parse', '--verify', f'refs/tags/{tag}^{{commit}}'), tag


def preview(root, site, version):
    config = sites(root)
    if site not in config:
        raise RecoveryError('未知站台，禁止操作分支。')
    selected = config[site]
    head = git(root, 'rev-parse', '--verify', f"refs/remotes/origin/{selected['branch']}^{{commit}}")
    source, tag = snapshot(root, site, version)
    git(root, 'cat-file', '-e', source + ':' + selected['entry'])
    changed = git(root, 'diff', '--name-only', head, source).splitlines()
    changed = [path for path in changed if path not in CONTROL_FILES]
    return {'site': site, 'branch': selected['branch'], 'entry': selected['entry'], 'head': head,
            'source': source, 'version': tag, 'changed_files': changed, 'url': selected.get('url', '')}


def validate_tree(tree):
    for args in ([sys.executable, '-m', 'compileall', '-q', '.'], [sys.executable, '-m', 'pytest', '-q']):
        if subprocess.run(args, cwd=tree).returncode:
            raise RecoveryError('目標版本的編譯或測試未通過，未發布回復。')


def apply(root, plan, *, expected_head, confirm_site, validator=validate_tree):
    if confirm_site != plan['site']:
        raise RecoveryError('確認站台名稱不一致，未發布回復。')
    fetch(root)
    fresh = preview(root, plan['site'], plan['version'])
    if expected_head != fresh['head'] or fresh['head'] != plan['head'] or fresh['source'] != plan['source']:
        raise RecoveryError('預覽後遠端版本已變更，請重新預覽再回復。')
    if not fresh['changed_files']:
        return {**fresh, 'status': 'already_current'}
    with tempfile.TemporaryDirectory(prefix='settlement-recovery-') as directory:
        tree = Path(directory) / 'tree'
        git(root, 'worktree', 'add', '--detach', str(tree), fresh['head'])
        try:
            git(tree, 'read-tree', '--reset', '-u', fresh['source'])
            for path in CONTROL_FILES:
                # Keep recovery controls available after restoring an older app version.
                exists = subprocess.run(['git', '-C', str(tree), 'cat-file', '-e', fresh['head'] + ':' + path], capture_output=True).returncode == 0
                if exists:
                    git(tree, 'restore', '--source=' + fresh['head'], '--staged', '--worktree', '--', path)
            validator(tree)
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            backup = f"rollback-backup/{fresh['site']}/{stamp}-{fresh['head'][:8]}-{uuid4().hex[:8]}"
            git(tree, '-c', 'user.name=Settlement Release Recovery', '-c', 'user.email=release-recovery@users.noreply.github.com',
                'commit', '-m', f"Restore {fresh['site']} to {fresh['version']}",
                '-m', f"Previous: {fresh['head']}\nSnapshot: {fresh['source']}\nBackup: {backup}")
            commit = git(tree, 'rev-parse', 'HEAD')
            git(root, 'tag', backup, fresh['head'])
            # Both refs publish together. A concurrent update rejects the branch push;
            # no --force/--force-with-lease is ever used, and no remote history is rewritten.
            git(tree, 'push', '--atomic', 'origin', f'HEAD:refs/heads/{fresh["branch"]}', f'refs/tags/{backup}:refs/tags/{backup}')
            return {**fresh, 'status': 'published', 'commit': commit, 'backup': backup}
        finally:
            git(root, 'worktree', 'remove', '--force', str(tree))


def main():
    parser = argparse.ArgumentParser(description='四站版本預覽與快速回復（僅儲存庫管理者）')
    parser.add_argument('action', choices=['list', 'preview', 'apply'])
    parser.add_argument('--site', choices=list(sites()), required=True)
    parser.add_argument('--version')
    parser.add_argument('--confirm-site')
    parser.add_argument('--expected-head')
    args = parser.parse_args()
    try:
        fetch(ROOT)
        if args.action == 'list':
            tags = git(ROOT, 'for-each-ref', '--format=%(refname:short) %(objectname)',
                       f'refs/tags/release/{args.site}/', f'refs/tags/rollback-backup/{args.site}/')
            print(tags or '此站尚未建立版本標籤。')
            return
        if not args.version:
            raise RecoveryError('請指定要回復的 --version。')
        plan = preview(ROOT, args.site, args.version)
        result = plan if args.action == 'preview' else apply(ROOT, plan, expected_head=args.expected_head, confirm_site=args.confirm_site)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except RecoveryError as exc:
        print(f'回復已停止：{exc}', file=sys.stderr)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
