const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');


const callScript = fs.readFileSync(
    path.join(__dirname, '../web/static/js/call.js'),
    'utf8',
);


class FakeElement {
    constructor(id) {
        this.id = id;
        this.disabled = false;
        this.listeners = new Map();
        this.active = id === 'loading-screen';
        this.classList = {
            add: (name) => {
                if (name === 'active') this.active = true;
            },
            remove: (name) => {
                if (name === 'active') this.active = false;
            },
            toggle: () => {},
        };
    }

    addEventListener(name, handler) {
        this.listeners.set(name, handler);
    }

    setAttribute() {}

    querySelector() {
        return { textContent: this.id === 'toggle-audio' ? 'Микрофон' : 'Камера' };
    }
}


function createRuntime({ localStorageThrows = false, userAgent = 'Desktop Browser' } = {}) {
    const elements = new Map();
    for (const id of [
        'toggle-audio',
        'toggle-video',
        'switch-camera',
        'end-call',
        'activate-here',
        'retry-connection',
        'retry-permissions',
        'jitsi-container',
        'loading-screen',
        'jitsi-screen',
        'finished-screen',
        'other-tab-screen',
        'connection-error-screen',
        'permission-error-screen',
    ]) {
        elements.set(id, new FakeElement(id));
    }

    let coordinatorOptions = null;
    let coordinatorDestroyCount = 0;
    const windowListeners = new Map();
    const documentListeners = new Map();
    const fetchCalls = [];
    const apiInstances = [];
    const iframeMessages = [];
    const executedCommands = [];
    const iframe = {
        contentWindow: {
            postMessage: (message, targetOrigin) => iframeMessages.push({ message, targetOrigin }),
        },
        removeAttribute() {},
        setAttribute() {},
    };
    const timeoutCallbacks = [];
    let reloadCount = 0;

    class FakeJitsiApi {
        constructor(_domain, options) {
            this.options = options;
            this.listeners = new Map();
            this.disposed = false;
            apiInstances.push(this);
        }

        addEventListener(name, handler) {
            this.listeners.set(name, handler);
        }

        executeCommand(command) {
            executedCommands.push(command);
        }

        dispose() {
            this.disposed = true;
            // Jitsi may emit this synchronously while dispose() is running.
            this.listeners.get('videoConferenceLeft')?.();
        }

        emit(name, payload) {
            this.listeners.get(name)?.(payload);
        }
    }

    const windowObject = {
        CALL_CONFIG: {
            jitsiDomain: 'meet.example.test',
            callId: 101,
            displayName: 'Alice',
            hangupUrl: '/secret-token/hangup',
            statusUrl: '/secret-token/status',
            transportUrl: '/secret-token/transport',
        },
        EchoCallTabCoordinator: {
            create(options) {
                coordinatorOptions = options;
                return {
                    start() {},
                    destroy() {
                        coordinatorDestroyCount += 1;
                    },
                };
            },
        },
        crypto: {
            randomUUID: () => 'tab-a',
        },
        navigator: {
            locks: { request() {} },
            userAgent,
        },
        addEventListener(name, handler) {
            windowListeners.set(name, handler);
        },
        clearInterval() {},
        clearTimeout() {},
        setInterval: () => 1,
        setTimeout(callback) {
            timeoutCallbacks.push(callback);
            return timeoutCallbacks.length;
        },
        location: {
            reload() {
                reloadCount += 1;
            },
        },
    };

    Object.defineProperty(windowObject, 'localStorage', {
        get() {
            if (localStorageThrows) {
                throw new Error('storage blocked');
            }
            return {
                getItem: () => null,
                setItem() {},
            };
        },
    });

    const documentObject = {
        visibilityState: 'visible',
        addEventListener(name, handler) {
            documentListeners.set(name, handler);
        },
        getElementById: (id) => elements.get(id) || null,
        querySelector: (selector) => (
            selector === '#jitsi-container' ? elements.get('jitsi-container')
                : selector === '#jitsi-container iframe' ? iframe
                    : null
        ),
        querySelectorAll: () => Array.from(elements.values()),
    };

    const context = {
        JitsiMeetExternalAPI: FakeJitsiApi,
        console,
        document: documentObject,
        fetch: async (...args) => {
            fetchCalls.push(args);
            return { ok: true, json: async () => ({ should_close: false }) };
        },
        window: windowObject,
    };

    vm.runInNewContext(callScript, context);

    return {
        apiInstances,
        executedCommands,
        document: documentObject,
        elements,
        fetchCalls,
        iframeMessages,
        documentListeners,
        windowListeners,
        runTimeouts() {
            timeoutCallbacks.splice(0).forEach((callback) => callback());
        },
        getCoordinatorOptions: () => coordinatorOptions,
        getCoordinatorDestroyCount: () => coordinatorDestroyCount,
        getReloadCount: () => reloadCount,
    };
}


test('call.js waits for ownership before constructing Jitsi', () => {
    const runtime = createRuntime();
    assert.equal(runtime.apiInstances.length, 0);

    runtime.getCoordinatorOptions().onStart();
    assert.equal(runtime.apiInstances.length, 1);
    assert.equal(runtime.elements.get('loading-screen').active, true);
    assert.equal(runtime.elements.get('jitsi-screen').active, false);

    runtime.apiInstances[0].emit('videoConferenceJoined');
    runtime.apiInstances[0].emit('videoMuteStatusChanged', { muted: false });
    assert.deepEqual(JSON.parse(JSON.stringify(runtime.iframeMessages.at(-1))), {
        message: { type: 'echocall:local-video-active', active: true },
        targetOrigin: 'https://meet.example.test',
    });
    assert.equal(runtime.elements.get('loading-screen').active, true);
    assert.equal(runtime.elements.get('jitsi-screen').active, false);

    runtime.runTimeouts();
    assert.equal(runtime.elements.get('loading-screen').active, false);
    assert.equal(runtime.elements.get('jitsi-screen').active, true);
});


test('superseding a joined call disposes Jitsi without sending hangup', async () => {
    const runtime = createRuntime();
    const coordinatorOptions = runtime.getCoordinatorOptions();
    coordinatorOptions.onStart();
    runtime.apiInstances[0].emit('videoConferenceJoined');

    coordinatorOptions.onSuperseded({ started: true });
    await Promise.resolve();

    assert.equal(runtime.apiInstances[0].disposed, true);
    assert.deepEqual(runtime.fetchCalls, []);
});


test('unexpected Jitsi exit does not end an active EchoCall', async () => {
    const runtime = createRuntime();
    runtime.getCoordinatorOptions().onStart();
    runtime.apiInstances[0].emit('videoConferenceJoined');

    runtime.apiInstances[0].emit('videoConferenceLeft');
    await Promise.resolve();

    assert.deepEqual(runtime.fetchCalls, []);
});


test('red end-call control still sends an explicit hangup', async () => {
    const runtime = createRuntime();
    runtime.getCoordinatorOptions().onStart();
    runtime.apiInstances[0].emit('videoConferenceJoined');

    runtime.elements.get('end-call').listeners.get('click')();
    assert.equal(runtime.elements.get('loading-screen').active, true);
    assert.equal(runtime.elements.get('finished-screen').active, false);
    await new Promise((resolve) => setImmediate(resolve));

    assert.equal(runtime.fetchCalls.length, 1);
    assert.equal(runtime.fetchCalls[0][0], '/secret-token/hangup');
    assert.equal(runtime.fetchCalls[0][1].method, 'POST');
    assert.equal(runtime.fetchCalls[0][1].headers['X-EchoCall-Explicit-Hangup'], '1');
    assert.equal(runtime.elements.get('finished-screen').active, true);
});


test('blocked localStorage falls back to a normal single call', () => {
    const runtime = createRuntime({ localStorageThrows: true });
    assert.equal(runtime.apiInstances.length, 1);
    assert.equal(runtime.getCoordinatorOptions(), null);
});


test('Jitsi P2P status is reported without exposing room data', async () => {
    const runtime = createRuntime();
    runtime.getCoordinatorOptions().onStart();
    runtime.apiInstances[0].emit('p2pStatusChanged', { p2p: true });
    await new Promise((resolve) => setImmediate(resolve));

    assert.equal(runtime.fetchCalls.length, 1);
    assert.equal(runtime.fetchCalls[0][0], '/secret-token/transport');
    assert.equal(runtime.fetchCalls[0][1].method, 'POST');
    assert.deepEqual(JSON.parse(runtime.fetchCalls[0][1].body), { mode: 'p2p' });
});


test('pagehide disposes the old Jitsi participant without ending EchoCall', async () => {
    const runtime = createRuntime();
    runtime.getCoordinatorOptions().onStart();
    runtime.apiInstances[0].emit('videoConferenceJoined');

    runtime.windowListeners.get('pagehide')();
    runtime.windowListeners.get('beforeunload')();
    await Promise.resolve();

    assert.equal(runtime.apiInstances[0].disposed, true);
    assert.equal(runtime.getCoordinatorDestroyCount(), 1);
    assert.deepEqual(runtime.fetchCalls, []);
    assert.equal(runtime.elements.get('loading-screen').active, true);
});


test('blocked-storage fallback also disposes Jitsi on pagehide', () => {
    const runtime = createRuntime({ localStorageThrows: true });
    runtime.windowListeners.get('pagehide')();

    assert.equal(runtime.apiInstances[0].disposed, true);
    assert.deepEqual(runtime.fetchCalls, []);
    assert.equal(runtime.elements.get('loading-screen').active, true);
    assert.equal(runtime.elements.get('connection-error-screen').active, false);
});


test('iPhone automatically recreates Jitsi media after returning to the call', async () => {
    const runtime = createRuntime({
        userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)',
    });
    runtime.getCoordinatorOptions().onStart();
    runtime.apiInstances[0].emit('videoConferenceJoined');
    runtime.apiInstances[0].emit('audioMuteStatusChanged', { muted: false });
    runtime.apiInstances[0].emit('videoMuteStatusChanged', { muted: false });

    runtime.document.visibilityState = 'hidden';
    runtime.documentListeners.get('visibilitychange')();
    runtime.document.visibilityState = 'visible';
    runtime.documentListeners.get('visibilitychange')();
    assert.equal(runtime.apiInstances[0].disposed, true);
    assert.equal(runtime.elements.get('loading-screen').active, true);

    runtime.runTimeouts();
    await Promise.resolve();

    assert.equal(runtime.apiInstances.length, 2);
    assert.equal(runtime.apiInstances[1].options.configOverwrite.startWithAudioMuted, false);
    assert.equal(runtime.apiInstances[1].options.configOverwrite.startWithVideoMuted, false);
    assert.deepEqual(runtime.fetchCalls, []);
});


test('repeated iPhone resume signals start only one media recovery', async () => {
    const runtime = createRuntime({
        userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)',
    });
    runtime.getCoordinatorOptions().onStart();
    runtime.apiInstances[0].emit('videoConferenceJoined');

    runtime.windowListeners.get('blur')();
    runtime.windowListeners.get('focus')();
    runtime.windowListeners.get('pageshow')({ persisted: false });
    runtime.documentListeners.get('visibilitychange')();
    runtime.runTimeouts();
    await Promise.resolve();

    assert.equal(runtime.apiInstances.length, 2);
    assert.deepEqual(runtime.fetchCalls, []);
});


test('late exit from recovered iPhone iframe does not replace the new call with an error', async () => {
    const runtime = createRuntime({
        userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)',
    });
    runtime.getCoordinatorOptions().onStart();
    runtime.apiInstances[0].emit('videoConferenceJoined');

    runtime.document.visibilityState = 'hidden';
    runtime.documentListeners.get('visibilitychange')();
    runtime.document.visibilityState = 'visible';
    runtime.documentListeners.get('visibilitychange')();
    runtime.runTimeouts();
    await Promise.resolve();
    runtime.apiInstances[1].emit('videoConferenceJoined');
    runtime.runTimeouts();

    runtime.apiInstances[0].emit('videoConferenceLeft');

    assert.equal(runtime.elements.get('jitsi-screen').active, true);
    assert.equal(runtime.elements.get('connection-error-screen').active, false);
});


test('desktop visibility changes do not recreate Jitsi media', async () => {
    const runtime = createRuntime();
    runtime.getCoordinatorOptions().onStart();
    runtime.apiInstances[0].emit('videoConferenceJoined');

    runtime.document.visibilityState = 'hidden';
    runtime.documentListeners.get('visibilitychange')();
    runtime.document.visibilityState = 'visible';
    runtime.documentListeners.get('visibilitychange')();
    runtime.runTimeouts();
    await Promise.resolve();

    assert.equal(runtime.apiInstances.length, 1);
    assert.equal(runtime.apiInstances[0].disposed, false);
});


test('mobile switch-camera control uses the Jitsi toggleCamera command', async () => {
    const runtime = createRuntime({
        userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)',
    });
    runtime.getCoordinatorOptions().onStart();
    runtime.apiInstances[0].emit('videoConferenceJoined');
    runtime.apiInstances[0].emit('videoMuteStatusChanged', { muted: false });

    const switchCameraButton = runtime.elements.get('switch-camera');
    assert.equal(switchCameraButton.hidden, false);
    assert.equal(switchCameraButton.disabled, false);
    switchCameraButton.listeners.get('click')();
    await Promise.resolve();

    assert.deepEqual(runtime.executedCommands, ['toggleCamera']);
});


test('returning from iOS back-forward cache reloads disposed call page', () => {
    const runtime = createRuntime();
    runtime.getCoordinatorOptions().onStart();
    runtime.windowListeners.get('pagehide')();
    runtime.windowListeners.get('pageshow')({ persisted: true });
    runtime.windowListeners.get('pageshow')({ persisted: false });
    assert.equal(runtime.apiInstances[0].disposed, true);
    assert.equal(runtime.elements.get('loading-screen').active, true);
    assert.equal(runtime.getReloadCount(), 1);
});


test('switch-camera control stays hidden on desktop browsers', () => {
    const runtime = createRuntime();
    assert.equal(runtime.elements.get('switch-camera').hidden, true);
});
