(function (root, factory) {
    const exported = factory();

    if (typeof module === 'object' && module.exports) {
        module.exports = exported;
    } else {
        root.EchoCallTabCoordinator = exported;
    }
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    const STORAGE_KEY = 'echocall.active-media-tab.v2';
    const LOCK_NAME = 'echocall.active-media.v1';

    function parseClaim(value) {
        try {
            const claim = JSON.parse(value || 'null');
            if (
                claim
                && typeof claim.tabId === 'string'
                && typeof claim.rank === 'string'
            ) {
                return claim;
            }
        } catch (error) {
            // Invalid or unavailable storage must not break a call.
        }
        return null;
    }

    function create(options) {
        const windowObject = options.windowObject;
        const storage = options.storage;
        const locks = options.locks;
        const onStart = options.onStart;
        const onSuperseded = options.onSuperseded;
        const fallbackDelay = options.fallbackDelay || 1000;
        const tabId = options.tabId;

        let ownClaim = null;
        let started = false;
        let superseded = false;
        let releaseLock = null;
        let fallbackTimer = null;

        function readCurrentClaim() {
            try {
                return parseClaim(storage.getItem(STORAGE_KEY));
            } catch (error) {
                return null;
            }
        }

        function isNewerForeignClaim(claim) {
            return Boolean(
                claim
                && claim.tabId !== tabId
                && ownClaim
                && claim.rank > ownClaim.rank
            );
        }

        function supersede() {
            if (superseded) {
                return;
            }

            superseded = true;
            if (fallbackTimer) {
                windowObject.clearTimeout(fallbackTimer);
                fallbackTimer = null;
            }
            onSuperseded({ started: started });
            if (releaseLock) {
                releaseLock();
                releaseLock = null;
            }
        }

        function handleStorage(event) {
            if (event.key === STORAGE_KEY) {
                const claim = parseClaim(event.newValue);
                if (isNewerForeignClaim(claim)) {
                    supersede();
                }
            }
        }

        function writeClaim() {
            const currentClaim = readCurrentClaim();
            const currentSequence = currentClaim
                ? Number(currentClaim.rank.split(':', 1)[0]) || 0
                : 0;
            const sequence = Math.max(Date.now(), currentSequence + 1);
            const rank = `${String(sequence).padStart(13, '0')}:${tabId}`;
            ownClaim = { tabId: tabId, rank: rank };
            try {
                storage.setItem(STORAGE_KEY, JSON.stringify(ownClaim));
            } catch (error) {
                // The Web Lock still serializes media when storage is blocked.
            }
        }

        function startIfStillOwner() {
            if (superseded || started) {
                return;
            }
            const currentClaim = readCurrentClaim();
            if (isNewerForeignClaim(currentClaim)) {
                supersede();
                return;
            }
            started = true;
            onStart();
        }

        async function holdWebLock() {
            await locks.request(LOCK_NAME, { mode: 'exclusive' }, async function () {
                if (superseded) {
                    return;
                }
                startIfStillOwner();
                await new Promise(function (resolve) {
                    releaseLock = resolve;
                });
            });
        }

        function start() {
            windowObject.addEventListener('storage', handleStorage);
            writeClaim();

            if (locks && typeof locks.request === 'function') {
                void holdWebLock().catch(function () {
                    if (!superseded && !started) {
                        fallbackTimer = windowObject.setTimeout(
                            startIfStillOwner,
                            fallbackDelay,
                        );
                    }
                });
                return;
            }

            // Legacy WebViews do not have Web Locks. Give the previous tab time
            // to process the storage event and release its Jitsi iframe first.
            fallbackTimer = windowObject.setTimeout(startIfStillOwner, fallbackDelay);
        }

        function destroy() {
            windowObject.removeEventListener('storage', handleStorage);
            if (fallbackTimer) {
                windowObject.clearTimeout(fallbackTimer);
                fallbackTimer = null;
            }
            if (releaseLock) {
                releaseLock();
                releaseLock = null;
            }
        }

        return {
            start: start,
            destroy: destroy,
            supersede: supersede,
        };
    }

    return {
        create: create,
        LOCK_NAME: LOCK_NAME,
        STORAGE_KEY: STORAGE_KEY,
    };
});
