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


if __name__ == '__main__':
    unittest.main()
