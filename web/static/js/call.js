(function () {
    const config = window.CALL_CONFIG || {};

    const domain = config.jitsiDomain;
    const roomName = config.callId;
    const displayName = config.displayName || 'User';
    const hangupUrl = config.hangupUrl;
    const statusUrl = config.statusUrl;
    const transportUrl = config.transportUrl;
    const transparentLogo = 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%221%22 height=%221%22/%3E';
    const audioButton = document.getElementById('toggle-audio');
    const videoButton = document.getElementById('toggle-video');
    const switchCameraButton = document.getElementById('switch-camera');
    const endCallButton = document.getElementById('end-call');
    const activateHereButton = document.getElementById('activate-here');
    const retryConnectionButton = document.getElementById('retry-connection');
    const retryPermissionsButton = document.getElementById('retry-permissions');
    const tabCoordinatorFactory = window.EchoCallTabCoordinator;
    const tabId = (
        window.crypto && typeof window.crypto.randomUUID === 'function'
            ? window.crypto.randomUUID()
            : `${Date.now()}-${Math.random().toString(16).slice(2)}`
    );
    const loadingStartedAt = Date.now();
    const minimumLoadingTime = 250;
    const joinedUiStabilizationTime = 100;
    const mediaRecoveryDelay = 350;
    const navigatorObject = window.navigator || {};
    const isIosDevice = /iPad|iPhone|iPod/.test(navigatorObject.userAgent || '')
        || (navigatorObject.platform === 'MacIntel' && navigatorObject.maxTouchPoints > 1);
    const isMobileDevice = isIosDevice || /Android/i.test(navigatorObject.userAgent || '');

    let api = null;
    let tabCoordinator = null;
    let hangupSent = false;
    let localCloseStarted = false;
    let closedByServer = false;
    let connected = false;
    let supersededByAnotherTab = false;
    let connectionTimer = null;
    let statusTimer = null;
    let reportedTransport = null;
    let pageExitStarted = false;
    let mediaRecoveryStarted = false;
    let recoverMediaWhenVisible = false;
    let audioMuted = false;
    let videoMuted = true;
    let screenWakeLock = null;

    if (switchCameraButton) {
        switchCameraButton.hidden = !isMobileDevice;
        switchCameraButton.disabled = true;
    }

    function showScreen(name) {
        document.querySelectorAll('.screen').forEach((screen) => {
            screen.classList.remove('active');
        });

        const screen = document.getElementById(`${name}-screen`);
        if (screen) {
            screen.classList.add('active');
        }
    }

    function getBrowserCapability(getter) {
        try {
            return getter();
        } catch (error) {
            return null;
        }
    }

    if (!domain || !roomName || !hangupUrl || !statusUrl) {
        showScreen('connection-error');
        return;
    }

    function buildJitsiOptions() {
        return {
            roomName: String(roomName),
            parentNode: document.querySelector('#jitsi-container'),
            width: '100%',
            height: '100%',
            userInfo: {
                displayName: displayName,
            },
            configOverwrite: {
                prejoinPageEnabled: false,
                prejoinConfig: {
                    enabled: false,
                },
                requireDisplayName: false,
                welcomePage: {
                    disabled: true,
                },
                disableDeepLinking: true,
                disableInviteFunctions: true,
                disableModeratorIndicator: true,
                feedbackPercentage: 0,
                hideConferenceSubject: true,
                hideConferenceTimer: true,
                defaultLogoUrl: transparentLogo,
                notifications: [],
                toolbarButtons: [],
                toolbarConfig: {
                    alwaysVisible: false,
                    initialTimeout: 0,
                    timeout: 0,
                },
                startWithAudioMuted: audioMuted,
                startWithVideoMuted: videoMuted,
            },
            interfaceConfigOverwrite: {
                SHOW_JITSI_WATERMARK: false,
                SHOW_BRAND_WATERMARK: false,
                SHOW_POWERED_BY: false,
                SHOW_WATERMARK_FOR_GUESTS: false,
                MOBILE_APP_PROMO: false,
                DEFAULT_LOGO_URL: '',
                DEFAULT_WELCOME_PAGE_LOGO_URL: '',
                DISPLAY_WELCOME_FOOTER: false,
                DISPLAY_WELCOME_PAGE_CONTENT: false,
                HIDE_DEEP_LINKING_LOGO: true,
                APP_NAME: 'Звонок',
                NATIVE_APP_NAME: 'Звонок',
                PROVIDER_NAME: 'Звонок',
            },
        };
    }

    function reloadWithLoadingScreen() {
        showScreen('loading');
        window.location.reload();
    }

    function delay(milliseconds) {
        return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
    }

    async function requestScreenWakeLock() {
        if (
            !connected
            || screenWakeLock
            || document.visibilityState === 'hidden'
            || !navigatorObject.wakeLock
            || typeof navigatorObject.wakeLock.request !== 'function'
        ) {
            return;
        }

        try {
            const lock = await navigatorObject.wakeLock.request('screen');
            screenWakeLock = lock;
            lock.addEventListener?.('release', () => {
                if (screenWakeLock === lock) {
                    screenWakeLock = null;
                }
            });
        } catch (error) {
            // Wake Lock is an optional mitigation. Calls must work without it.
            console.info('Screen Wake Lock is unavailable', error);
        }
    }

    function releaseScreenWakeLock() {
        const lock = screenWakeLock;
        screenWakeLock = null;
        if (lock && typeof lock.release === 'function') {
            try {
                void Promise.resolve(lock.release()).catch(() => {});
            } catch (error) {
                // The lock may already have been released by the browser.
            }
        }
    }

    function revealJoinedCall() {
        const remaining = Math.max(
            0,
            Math.max(minimumLoadingTime - (Date.now() - loadingStartedAt), joinedUiStabilizationTime),
        );
        window.setTimeout(() => {
            if (connected && !closedByServer && !supersededByAnotherTab) {
                showScreen('jitsi');
            }
        }, remaining);
    }

    function restrictJitsiIframeCapabilities() {
        const iframe = document.querySelector('#jitsi-container iframe');
        if (!iframe) {
            return;
        }
        iframe.removeAttribute('allowfullscreen');
        iframe.setAttribute('allow', 'camera; microphone; autoplay; display-capture');
    }

    function sendLocalVideoStateToJitsi(muted) {
        const iframe = document.querySelector('#jitsi-container iframe');
        if (!iframe || !iframe.contentWindow) {
            return;
        }
        iframe.contentWindow.postMessage({
            type: 'echocall:local-video-active',
            active: muted === false,
        }, `https://${domain}`);
    }

    async function notifyHangup(force = false) {
        if (supersededByAnotherTab) {
            return;
        }

        if (!connected && !force) {
            return;
        }

        if (closedByServer || hangupSent) {
            return;
        }

        hangupSent = true;

        try {
            const response = await fetch(hangupUrl, {
                method: 'POST',
                keepalive: true,
                headers: {
                    'X-EchoCall-Explicit-Hangup': '1',
                },
            });
            return response.ok;
        } catch (error) {
            console.error('Failed to notify hangup', error);
            return false;
        }
    }

    function setControlState(button, isOff, onLabel, offLabel) {
        if (!button) {
            return;
        }

        button.classList.toggle('is-off', isOff);
        button.setAttribute('aria-pressed', String(isOff));
        button.setAttribute('aria-label', isOff ? onLabel : offLabel);
    }

    async function toggleMedia(command, button) {
        if (!api || !button || button.disabled) {
            return;
        }

        button.disabled = true;
        try {
            await api.executeCommand(command);
        } catch (error) {
            console.error(`Failed to execute ${command}`, error);
        } finally {
            button.disabled = false;
        }
    }

    function markMediaInterrupted() {
        if (
            isIosDevice
            && connected
            && api
            && !mediaRecoveryStarted
            && !supersededByAnotherTab
            && !localCloseStarted
            && !closedByServer
        ) {
            recoverMediaWhenVisible = true;
        }
    }

    async function recoverMediaAfterInterruption() {
        if (
            !isIosDevice
            || !recoverMediaWhenVisible
            || !api
            || mediaRecoveryStarted
            || pageExitStarted
            || document.visibilityState === 'hidden'
            || supersededByAnotherTab
            || localCloseStarted
            || closedByServer
        ) {
            return;
        }

        recoverMediaWhenVisible = false;
        mediaRecoveryStarted = true;
        connected = false;
        showScreen('loading');

        if (connectionTimer) {
            window.clearTimeout(connectionTimer);
            connectionTimer = null;
        }
        if (statusTimer) {
            window.clearInterval(statusTimer);
            statusTimer = null;
        }

        const currentApi = api;
        api = null;
        try {
            currentApi.dispose();
        } catch (error) {
            console.error('Failed to restore Jitsi media after interruption', error);
        }

        await delay(mediaRecoveryDelay);
        if (pageExitStarted || supersededByAnotherTab || localCloseStarted || closedByServer) {
            mediaRecoveryStarted = false;
            return;
        }

        mediaRecoveryStarted = false;
        startJitsi();
    }

    function resumeCallAfterInterruption() {
        void requestScreenWakeLock();
        void recoverMediaAfterInterruption();
    }

    async function finishLocalCall(forceNotify = false) {
        if (supersededByAnotherTab || closedByServer || localCloseStarted) {
            return;
        }

        localCloseStarted = true;
        showScreen('loading');
        const confirmed = await notifyHangup(forceNotify);
        if (!confirmed) {
            localCloseStarted = false;
            hangupSent = false;
            showScreen('connection-error');
            return;
        }
        closedByServer = true;
        releaseScreenWakeLock();

        if (tabCoordinator) {
            tabCoordinator.destroy();
            tabCoordinator = null;
        }

        try {
            if (api) {
                api.dispose();
                api = null;
            }
        } catch (error) {
            console.error('Failed to leave Jitsi call', error);
        }
        showScreen('finished');
    }

    function closeCallFromServer() {
        if (closedByServer) {
            return;
        }

        closedByServer = true;
        releaseScreenWakeLock();

        if (tabCoordinator) {
            tabCoordinator.destroy();
            tabCoordinator = null;
        }

        try {
            if (api) {
                api.dispose();
                api = null;
            }
        } catch (error) {
            console.error('Failed to close Jitsi call', error);
        }

        showScreen('finished');
    }

    function handleUnexpectedConferenceExit(sourceApi) {
        if (
            sourceApi !== api
            ||
            pageExitStarted
            || mediaRecoveryStarted
            || supersededByAnotherTab
            || localCloseStarted
            || closedByServer
        ) {
            return;
        }

        connected = false;
        api = null;

        if (connectionTimer) {
            window.clearTimeout(connectionTimer);
            connectionTimer = null;
        }

        // A mobile browser can temporarily drop the Jitsi conference while the
        // EchoCall itself is still active. Never turn that transport event into
        // a server-side hangup; let the user reconnect with the same call link.
        showScreen('connection-error');
    }

    async function checkCallStatus() {
        if (supersededByAnotherTab || closedByServer) {
            return;
        }

        try {
            const response = await fetch(statusUrl, { cache: 'no-store' });

            if (!response.ok) {
                closeCallFromServer();
                return;
            }

            const data = await response.json();

            if (data.should_close) {
                closeCallFromServer();
            }
        } catch (error) {
            console.error('Failed to check call status', error);
        }
    }

    async function reportTransport(isP2p) {
        const mode = isP2p ? 'p2p' : 'jvb';
        if (!transportUrl || reportedTransport === mode) {
            return;
        }
        reportedTransport = mode;
        try {
            await fetch(transportUrl, {
                method: 'POST',
                keepalive: true,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode: mode }),
            });
        } catch (error) {
            reportedTransport = null;
            console.error('Failed to report call transport', error);
        }
    }

    if (audioButton) {
        audioButton.addEventListener('click', () => {
            void toggleMedia('toggleAudio', audioButton);
        });
    }

    if (videoButton) {
        videoButton.addEventListener('click', () => {
            void toggleMedia('toggleVideo', videoButton);
        });
    }

    if (switchCameraButton) {
        switchCameraButton.addEventListener('click', () => {
            void toggleMedia('toggleCamera', switchCameraButton);
        });
    }

    if (endCallButton) {
        endCallButton.addEventListener('click', () => {
            void finishLocalCall(true);
        });
    }

    if (activateHereButton) {
        activateHereButton.addEventListener('click', reloadWithLoadingScreen);
    }

    if (retryConnectionButton) {
        retryConnectionButton.addEventListener('click', reloadWithLoadingScreen);
    }

    if (retryPermissionsButton) {
        retryPermissionsButton.addEventListener('click', reloadWithLoadingScreen);
    }

    function stopJitsiForAnotherTab() {
        if (supersededByAnotherTab || localCloseStarted || closedByServer) {
            return;
        }

        supersededByAnotherTab = true;
        connected = false;
        recoverMediaWhenVisible = false;
        releaseScreenWakeLock();
        if (connectionTimer) {
            window.clearTimeout(connectionTimer);
            connectionTimer = null;
        }
        if (statusTimer) {
            window.clearInterval(statusTimer);
            statusTimer = null;
        }

        const currentApi = api;
        api = null;
        if (currentApi) {
            try {
                currentApi.dispose();
            } catch (error) {
                console.error('Failed to release Jitsi for another tab', error);
            }
        }

        showScreen('other-tab');
    }

    function teardownForPageExit() {
        if (pageExitStarted) {
            return;
        }

        pageExitStarted = true;
        connected = false;
        recoverMediaWhenVisible = false;
        releaseScreenWakeLock();

        if (connectionTimer) {
            window.clearTimeout(connectionTimer);
            connectionTimer = null;
        }
        if (statusTimer) {
            window.clearInterval(statusTimer);
            statusTimer = null;
        }

        // Explicitly dispose the iframe before releasing media ownership. If
        // the browser reloads the page without this step, the old Jitsi/XMPP
        // participant can remain visible until its network timeout expires.
        const currentApi = api;
        api = null;
        if (currentApi) {
            try {
                currentApi.dispose();
            } catch (error) {
                console.error('Failed to dispose Jitsi while leaving the page', error);
            }
        }

        if (tabCoordinator) {
            tabCoordinator.destroy();
            tabCoordinator = null;
        }
    }

    function startJitsi() {
        if (supersededByAnotherTab || api) {
            return;
        }

        let currentApi;
        try {
            currentApi = new JitsiMeetExternalAPI(domain, buildJitsiOptions());
            api = currentApi;
            restrictJitsiIframeCapabilities();
        } catch (error) {
            console.error('Failed to create Jitsi API', error);
            showScreen('connection-error');
            return;
        }

        currentApi.addEventListener('videoConferenceJoined', () => {
            if (supersededByAnotherTab || api !== currentApi) {
                return;
            }
            connected = true;
            mediaRecoveryStarted = false;
            sendLocalVideoStateToJitsi(true);
            revealJoinedCall();
            void requestScreenWakeLock();
        });

        currentApi.addEventListener('p2pStatusChanged', (event) => {
            if (api === currentApi && !supersededByAnotherTab && !closedByServer) {
                void reportTransport(Boolean(event && event.p2p));
            }
        });

        currentApi.addEventListener('audioMuteStatusChanged', (event) => {
            if (api !== currentApi) {
                return;
            }
            audioMuted = Boolean(event && event.muted);
            setControlState(audioButton, event.muted, 'Включить микрофон', 'Выключить микрофон');
        });

        currentApi.addEventListener('videoMuteStatusChanged', (event) => {
            if (api !== currentApi) {
                return;
            }
            videoMuted = Boolean(event && event.muted);
            setControlState(videoButton, event.muted, 'Включить камеру', 'Выключить камеру');
            if (switchCameraButton) {
                switchCameraButton.disabled = videoMuted;
            }
            sendLocalVideoStateToJitsi(event.muted);
        });

        currentApi.addEventListener('readyToClose', () => handleUnexpectedConferenceExit(currentApi));
        currentApi.addEventListener('videoConferenceLeft', () => handleUnexpectedConferenceExit(currentApi));

        currentApi.addEventListener('cameraError', () => {
            if (api === currentApi && !supersededByAnotherTab) {
                showScreen('permission-error');
            }
        });

        currentApi.addEventListener('micError', () => {
            if (api === currentApi && !supersededByAnotherTab) {
                showScreen('permission-error');
            }
        });

        connectionTimer = window.setTimeout(() => {
            if (!connected && !closedByServer && !supersededByAnotherTab) {
                showScreen('connection-error');
            }
        }, 20000);

        statusTimer = window.setInterval(checkCallStatus, 3000);
    }

    window.addEventListener('beforeunload', () => {
        showScreen('loading');
        teardownForPageExit();
    });

    window.addEventListener('pagehide', () => {
        showScreen('loading');
        teardownForPageExit();
    });

    window.addEventListener('pageshow', (event) => {
        if (event.persisted && pageExitStarted) {
            reloadWithLoadingScreen();
            return;
        }
        resumeCallAfterInterruption();
    });

    window.addEventListener('blur', markMediaInterrupted);
    window.addEventListener('focus', resumeCallAfterInterruption);

    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            resumeCallAfterInterruption();
        } else {
            markMediaInterrupted();
        }
    });

    if (!tabCoordinatorFactory || typeof tabCoordinatorFactory.create !== 'function') {
        startJitsi();
        return;
    }

    const browserStorage = getBrowserCapability(() => window.localStorage);
    const browserLocks = getBrowserCapability(() => (
        window.navigator ? window.navigator.locks : null
    ));

    if (!browserStorage) {
        startJitsi();
        return;
    }

    tabCoordinator = tabCoordinatorFactory.create({
        windowObject: window,
        storage: browserStorage,
        locks: browserLocks,
        tabId: tabId,
        fallbackDelay: 1200,
        onStart: startJitsi,
        onSuperseded: stopJitsiForAnotherTab,
    });
    tabCoordinator.start();
})();
