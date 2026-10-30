const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const script = fs.readFileSync(
    path.join(__dirname, '../docker/jitsi-web/echocall-embedded.js'),
    'utf8',
);

test('embedded self-view starts safely, drags, and remains clamped', () => {
    const windowListeners = new Map();
    const elementListeners = new Map();
    const classes = new Set();
    const styles = new Map();
    const dispatchedActions = [];
    let appendedSelfView = null;
    const settings = { disableSelfView: true };
    const localMediaTrack = { enabled: true, readyState: 'live' };
    const video = {
        srcObject: null,
        play: () => Promise.resolve(),
    };
    const selfView = {
        id: '',
        isConnected: true,
        appendChild: (child) => { selfView.video = child; },
        addEventListener: (name, handler) => elementListeners.set(name, handler),
        classList: {
            add: (name) => classes.add(name),
            remove: (name) => classes.delete(name),
            toggle: (name, active) => active ? classes.add(name) : classes.delete(name),
        },
        getBoundingClientRect: () => ({ width: 120, height: 160 }),
        setPointerCapture: () => {},
        style: {
            setProperty: (name, value) => styles.set(name, value),
        },
    };
    const document = {
        referrer: 'https://app.example.test/capability',
        documentElement: { classList: { add: (name) => classes.add(name) } },
        body: {
            appendChild: (element) => { appendedSelfView = element; },
        },
        createElement: (tagName) => tagName === 'video' ? video : selfView,
        getElementById: () => null,
        querySelector: () => null,
    };
    const windowObject = {
        innerWidth: 400,
        innerHeight: 800,
        self: {},
        top: {},
        addEventListener: (name, handler) => windowListeners.set(name, handler),
        requestAnimationFrame: (callback) => callback(),
        setInterval: () => 1,
        parent: {},
        APP: {
            conference: {
                getLocalTracks: () => [{
                    getType: () => 'video',
                    getTrack: () => localMediaTrack,
                }],
            },
            store: {
                dispatch: (action) => {
                    dispatchedActions.push(action);
                    Object.assign(settings, action.settings);
                },
                getState: () => ({ 'features/base/settings': settings }),
            },
        },
    };
    class FakeMutationObserver {
        constructor(callback) {
            this.callback = callback;
        }
        observe() {}
    }
    class FakeMediaStream {
        constructor(tracks) {
            this.tracks = tracks;
        }
        getVideoTracks() {
            return this.tracks;
        }
    }

    vm.runInNewContext(script, {
        document,
        window: windowObject,
        MediaStream: FakeMediaStream,
        MutationObserver: FakeMutationObserver,
        URL,
    });

    assert.equal(classes.has('echocall-embedded-call'), true);
    assert.equal(dispatchedActions.length, 1);
    assert.equal(dispatchedActions[0].type, 'SETTINGS_UPDATED');
    assert.equal(dispatchedActions[0].settings.disableSelfView, false);
    assert.equal(settings.disableSelfView, false);
    assert.equal(appendedSelfView, selfView);
    assert.equal(selfView.id, 'echocall-self-view');
    assert.equal(selfView.video, video);
    assert.equal(video.autoplay, true);
    assert.equal(video.muted, true);
    assert.equal(video.playsInline, true);
    assert.equal(video.srcObject.getVideoTracks()[0], localMediaTrack);
    assert.equal(classes.has('echocall-self-view-video-active'), true);
    assert.equal(styles.get('transform'), 'translate3d(268px, 96px, 0)');

    elementListeners.get('pointerdown')({
        button: 0,
        pointerId: 1,
        clientX: 280,
        clientY: 110,
        preventDefault() {},
        stopPropagation() {},
    });
    windowListeners.get('pointermove')({
        pointerId: 1,
        clientX: -1000,
        clientY: 2000,
        preventDefault() {},
    });

    assert.equal(styles.get('transform'), 'translate3d(12px, 508px, 0)');
    assert.equal(classes.has('echocall-self-view-dragging'), true);
    windowListeners.get('pointerup')({ pointerId: 1 });
    assert.equal(classes.has('echocall-self-view-dragging'), false);

    windowListeners.get('message')({
        source: windowObject.parent,
        origin: 'https://app.example.test',
        data: { type: 'echocall:local-video-active', active: false },
    });
    assert.equal(classes.has('echocall-self-view-video-active'), false);
    windowListeners.get('message')({
        source: windowObject.parent,
        origin: 'https://attacker.invalid',
        data: { type: 'echocall:local-video-active', active: true },
    });
    assert.equal(classes.has('echocall-self-view-video-active'), false);
});
