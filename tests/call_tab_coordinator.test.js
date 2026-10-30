const assert = require('node:assert/strict');
const test = require('node:test');

const coordinatorModule = require('../web/static/js/call-tab-coordinator.js');


function flushPromises() {
    return new Promise((resolve) => setImmediate(resolve));
}


class FakeWindow {
    constructor() {
        this.listeners = new Map();
        this.timers = [];
    }

    addEventListener(name, handler) {
        if (!this.listeners.has(name)) {
            this.listeners.set(name, new Set());
        }
        this.listeners.get(name).add(handler);
    }

    removeEventListener(name, handler) {
        this.listeners.get(name)?.delete(handler);
    }

    dispatch(name, event) {
        for (const handler of this.listeners.get(name) || []) {
            handler(event);
        }
    }

    setTimeout(handler) {
        this.timers.push(handler);
        return this.timers.length;
    }

    clearTimeout(timerId) {
        this.timers[timerId - 1] = null;
    }

    runTimers() {
        const timers = this.timers.splice(0);
        for (const timer of timers) {
            if (timer) {
                timer();
            }
        }
    }
}


class SharedStorage {
    constructor() {
        this.value = null;
        this.windows = [];
    }

    connect(windowObject) {
        this.windows.push(windowObject);
        return {
            getItem: () => this.value,
            setItem: (key, value) => {
                this.value = value;
                for (const target of this.windows) {
                    if (target !== windowObject) {
                        target.dispatch('storage', { key, newValue: value });
                    }
                }
            },
        };
    }
}


class FakeLocks {
    constructor() {
        this.active = false;
        this.queue = [];
    }

    request(_name, _options, callback) {
        return new Promise((resolve, reject) => {
            this.queue.push({ callback, resolve, reject });
            this.runNext();
        });
    }

    runNext() {
        if (this.active || this.queue.length === 0) {
            return;
        }
        this.active = true;
        const item = this.queue.shift();
        Promise.resolve()
            .then(item.callback)
            .then(item.resolve, item.reject)
            .finally(() => {
                this.active = false;
                this.runNext();
            });
    }
}


class RejectingLocks {
    request() {
        return Promise.reject(new Error('Web Locks unavailable'));
    }
}


function createTab({ tabId, windowObject, storage, locks, events }) {
    return coordinatorModule.create({
        tabId,
        windowObject,
        storage,
        locks,
        fallbackDelay: 1,
        onStart: () => events.push(`${tabId}:start`),
        onSuperseded: ({ started }) => events.push(`${tabId}:stop:${started}`),
    });
}


test('a single tab acquires the lock and starts once', async () => {
    const events = [];
    const windowObject = new FakeWindow();
    const sharedStorage = new SharedStorage();
    const tab = createTab({
        tabId: 'a',
        windowObject,
        storage: sharedStorage.connect(windowObject),
        locks: new FakeLocks(),
        events,
    });

    tab.start();
    await flushPromises();

    assert.deepEqual(events, ['a:start']);
    tab.destroy();
});


test('a second different call waits until the first releases media', async () => {
    const events = [];
    const locks = new FakeLocks();
    const sharedStorage = new SharedStorage();
    const windowA = new FakeWindow();
    const windowB = new FakeWindow();
    const tabA = createTab({
        tabId: 'a',
        windowObject: windowA,
        storage: sharedStorage.connect(windowA),
        locks,
        events,
    });
    const tabB = createTab({
        tabId: 'b',
        windowObject: windowB,
        storage: sharedStorage.connect(windowB),
        locks,
        events,
    });

    tabA.start();
    await flushPromises();
    tabB.start();

    assert.deepEqual(events, ['a:start', 'a:stop:true']);
    await flushPromises();
    await flushPromises();
    assert.deepEqual(events, ['a:start', 'a:stop:true', 'b:start']);

    tabA.destroy();
    tabB.destroy();
});


test('legacy fallback starts only the newest tab after the grace delay', () => {
    const events = [];
    const sharedStorage = new SharedStorage();
    const windowA = new FakeWindow();
    const windowB = new FakeWindow();
    const tabA = createTab({
        tabId: 'a',
        windowObject: windowA,
        storage: sharedStorage.connect(windowA),
        locks: null,
        events,
    });
    const tabB = createTab({
        tabId: 'b',
        windowObject: windowB,
        storage: sharedStorage.connect(windowB),
        locks: null,
        events,
    });

    tabA.start();
    tabB.start();
    windowA.runTimers();
    windowB.runTimers();

    assert.deepEqual(events, ['a:stop:false', 'b:start']);
    tabA.destroy();
    tabB.destroy();
});


test('a rejected Web Lock falls back without crashing a single call', async () => {
    const events = [];
    const windowObject = new FakeWindow();
    const sharedStorage = new SharedStorage();
    const tab = createTab({
        tabId: 'a',
        windowObject,
        storage: sharedStorage.connect(windowObject),
        locks: new RejectingLocks(),
        events,
    });

    tab.start();
    await flushPromises();
    windowObject.runTimers();

    assert.deepEqual(events, ['a:start']);
    tab.destroy();
});


test('a new claim ranks after an existing future claim', () => {
    const events = [];
    const windowObject = new FakeWindow();
    const sharedStorage = new SharedStorage();
    sharedStorage.value = JSON.stringify({
        tabId: 'old',
        rank: '9999999999999:old',
    });
    const tab = createTab({
        tabId: 'new',
        windowObject,
        storage: sharedStorage.connect(windowObject),
        locks: null,
        events,
    });

    tab.start();
    const claim = JSON.parse(sharedStorage.value);

    assert.equal(claim.rank, '10000000000000:new');
    tab.destroy();
});
