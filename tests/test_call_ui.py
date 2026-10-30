import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CallUiTests(unittest.TestCase):
    def test_call_page_uses_single_app_owned_hangup_control(self):
        template = (ROOT / 'web/templates/call.html').read_text(encoding='utf-8')
        script = (ROOT / 'web/static/js/call.js').read_text(encoding='utf-8')

        self.assertEqual(template.count('id="end-call"'), 1)
        self.assertIn("toolbarButtons: []", script)
        self.assertIn('prejoinPageEnabled: false', script)
        self.assertIn('requireDisplayName: false', script)
        self.assertIn('EchoCallTabCoordinator', script)
        self.assertIn('onStart: startJitsi', script)
        self.assertIn('onSuperseded: stopJitsiForAnotherTab', script)
        self.assertIn("showScreen('other-tab')", script)
        self.assertIn('supersededByAnotherTab', script)
        self.assertIn('call-tab-coordinator.js', template)
        self.assertIn("endCallButton.addEventListener('click'", script)
        self.assertIn("'X-EchoCall-Explicit-Hangup': '1'", script)
        self.assertIn("'p2pStatusChanged'", script)
        self.assertIn('transportUrl', template)
        self.assertIn('const minimumLoadingTime = 250', script)
        self.assertNotIn("label.textContent = isOff ? 'Выключено'", script)
        self.assertNotIn('buttonsWithNotifyClick', script)
        self.assertNotIn("'hangup',", script)

    def test_mobile_controls_have_accessible_labels_and_safe_area(self):
        template = (ROOT / 'web/templates/call.html').read_text(encoding='utf-8')
        stylesheet = (ROOT / 'web/static/css/app.css').read_text(encoding='utf-8')

        for control_id in ('toggle-audio', 'toggle-video', 'switch-camera', 'end-call'):
            self.assertIn(f'id="{control_id}"', template)
        self.assertNotIn('id="recover-microphone"', template)
        self.assertIn('Переключить камеру', template)
        self.assertIn('requestScreenWakeLock', (ROOT / 'web/static/js/call.js').read_text(encoding='utf-8'))
        self.assertIn('recoverMediaAfterInterruption', (ROOT / 'web/static/js/call.js').read_text(encoding='utf-8'))
        self.assertIn("toggleMedia('toggleCamera'", (ROOT / 'web/static/js/call.js').read_text(encoding='utf-8'))
        self.assertIn('id="other-tab-screen"', template)
        self.assertIn('id="activate-here"', template)
        self.assertIn('aria-label="Управление звонком"', template)
        self.assertIn('env(safe-area-inset-bottom)', stylesheet)
        self.assertIn('touch-action: manipulation', stylesheet)
        self.assertIn('visibility: hidden', stylesheet)
        self.assertIn('visibility: visible', stylesheet)
        self.assertIn('jitsi-native-chrome-mask-top', template)
        self.assertIn('jitsi-native-chrome-mask-bottom', template)
        self.assertIn('.jitsi-native-chrome-mask-top', stylesheet)
        self.assertIn('.jitsi-native-chrome-mask-bottom', stylesheet)
        self.assertIn("removeAttribute('allowfullscreen')", (ROOT / 'web/static/js/call.js').read_text(encoding='utf-8'))
        self.assertIn('teardownForPageExit', (ROOT / 'web/static/js/call.js').read_text(encoding='utf-8'))
        self.assertIn('.call-control.is-off:not(.call-control-end) .call-control-icon::after', stylesheet)

    def test_embedded_jitsi_image_hides_native_chrome(self):
        dockerfile = (ROOT / 'docker/jitsi-web/Dockerfile').read_text(encoding='utf-8')
        stylesheet = (ROOT / 'docker/jitsi-web/echocall-embedded.css').read_text(encoding='utf-8')
        embedded_script = (ROOT / 'docker/jitsi-web/echocall-embedded.js').read_text(encoding='utf-8')

        self.assertIn('ARG JITSI_WEB_BASE', dockerfile)
        self.assertIn('FROM ${JITSI_WEB_BASE}', dockerfile)
        self.assertNotIn('ARG JITSI_WEB_BASE=', dockerfile)
        self.assertIn('echocall-embedded.css', dockerfile)
        self.assertIn('echocall-embedded-ui', dockerfile)
        self.assertIn('echocall-embedded.js', dockerfile)
        self.assertNotIn('<link rel=', dockerfile)
        for selector in ('.subject-info-container', '.new-toolbox', '.toolbox-content'):
            self.assertIn(selector, stylesheet)
        self.assertIn('display: none !important', stylesheet)
        self.assertIn('#echocall-self-view', stylesheet)
        self.assertIn("selfView.id = 'echocall-self-view'", embedded_script)
        self.assertIn("document.createElement('video')", embedded_script)
        self.assertIn('getLocalTracks', embedded_script)
        self.assertIn("querySelector('#localVideo_container video')", embedded_script)
        self.assertIn("type: 'SETTINGS_UPDATED'", embedded_script)
        self.assertIn('settings: { disableSelfView: false }', embedded_script)
        self.assertIn('touch-action: none !important', stylesheet)
        self.assertIn("addEventListener('pointerdown'", embedded_script)
        self.assertIn('setPointerCapture', embedded_script)
        self.assertIn('applyPosition', embedded_script)
        self.assertNotIn('attributes: true', embedded_script)


if __name__ == '__main__':
    unittest.main()
