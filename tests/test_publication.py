import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PublicationTests(unittest.TestCase):
    def test_local_credentials_are_excluded_from_git_and_docker(self):
        gitignore = (ROOT / '.gitignore').read_text(encoding='utf-8')
        dockerignore = (ROOT / '.dockerignore').read_text(encoding='utf-8')
        for pattern in ('.env*', '*.local.*', '*.pem', '*.key', '*.dump',
                        'rclone.conf', 'restic-password', '*.db', '*.tar'):
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, gitignore.splitlines())
                self.assertIn(pattern, dockerignore.splitlines())
        for example in ('.env.example', '.env.rf.example', '.env.foreign.example'):
            self.assertIn(f'!{example}', gitignore.splitlines())
            self.assertTrue((ROOT / example).is_file())

    def test_ci_runs_tests_without_deploying(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
        self.assertIn('python -m unittest discover -s tests -v', workflow)
        self.assertIn('node --test', workflow)
        self.assertIn('contents: read', workflow)
        self.assertNotIn('secrets.', workflow)
        self.assertNotIn('ssh-action', workflow)
        self.assertFalse((ROOT / '.github/workflows/deploy.yml').exists())

    def test_personal_runtime_artifacts_are_not_distributed(self):
        for name in ('.env', '.env.rf', '.env.foreign', 'app.db',
                     '.cdp-eval.js', '.selfview-diagnostic.html',
                     'legal/telegraph-policy.local.json',
                     'scripts/publish-telegraph-policy.py'):
            with self.subTest(path=name):
                self.assertFalse((ROOT / name).exists())

    def test_access_logs_do_not_capture_capability_urls(self):
        for name in ('default.conf', 'rf.conf.template', 'foreign-gateway.conf.template'):
            text = (ROOT / 'docker/nginx' / name).read_text(encoding='utf-8')
            log_format = next(line for line in text.splitlines() if line.startswith('log_format '))
            for sensitive in ('$request_uri', '$request ', '$http_referer', '$args'):
                self.assertNotIn(sensitive, log_format)
        for name in ('docker-compose.yml', 'docker-compose.rf.yml', 'docker-compose.foreign.yml'):
            text = (ROOT / name).read_text(encoding='utf-8')
            self.assertIn('--access-logformat', text)
            self.assertIn('%(m)s %(s)s %(L)s', text)

    def test_application_container_runs_as_unprivileged_user(self):
        dockerfile = (ROOT / 'Dockerfile').read_text(encoding='utf-8')
        self.assertIn('USER 10001:10001', dockerfile)
        self.assertIn('Dependency vulnerability audit',
                      (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
