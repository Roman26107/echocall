import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeployScriptTests(unittest.TestCase):
    def test_rf_web_uses_project_unique_network_alias(self):
        compose = (ROOT / 'docker-compose.rf.yml').read_text(encoding='utf-8')
        config = (ROOT / 'docker/nginx/rf.conf.template').read_text(
            encoding='utf-8'
        )

        self.assertIn('- echocall-app-web', compose)
        self.assertIn('server echocall-app-web:8000;', config)
        self.assertNotIn('server web:8000;', config)

    def test_rf_deploy_refreshes_nginx_after_upstreams(self):
        script = (ROOT / 'scripts/deploy-role.sh').read_text(encoding='utf-8')

        upstream_up = 'up -d --no-build --remove-orphans'
        nginx_refresh = 'up -d --no-build --no-deps --force-recreate nginx'
        self.assertIn(nginx_refresh, script.replace('\\\n    ', ''))
        self.assertLess(script.index(upstream_up), script.index('force-recreate nginx'))

    def test_api_origin_exposes_call_ui_but_keeps_internal_api_restricted(self):
        config = (ROOT / 'docker/nginx/rf.conf.template').read_text(
            encoding='utf-8'
        )
        api_server = config.split(
            'server_name ${INTERNAL_API_DOMAIN};', 1
        )[1].split('server_name ${MEET_DOMAIN};', 1)[0]

        internal_location = api_server.split(
            'location /internal/v1/ {', 1
        )[1].split('location /static/ {', 1)[0]
        public_location = api_server.rsplit('location / {', 1)[1]

        self.assertIn('deny all;', internal_location)
        self.assertIn('proxy_pass http://echocall_internal_api;', internal_location)
        self.assertIn('location /static/ {', api_server)
        self.assertIn('proxy_pass http://echocall_web;', public_location)
        self.assertNotIn('deny all;', public_location)


if __name__ == '__main__':
    unittest.main()
