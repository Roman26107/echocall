(function () {
    'use strict';

    if (window.self === window.top) {
        return;
    }

    document.documentElement.classList.add('echocall-embedded-call');

    const sideInset = 12;
    const topInset = 96;
    const bottomInset = 132;
    let parentOrigin = null;
    try {
        parentOrigin = new URL(document.referrer).origin;
    } catch (error) {
        parentOrigin = null;
    }
    let selfView = null;
    let previewVideo = null;
    let sourceVideo = null;
    let cameraActiveFromParent = null;
    let drag = null;
    let position = null;

    function ensureSelfViewEnabled() {
        try {
            const store = window.APP?.store;
            const settings = store?.getState?.()['features/base/settings'];
            if (settings?.disableSelfView === true) {
                store.dispatch({
                    type: 'SETTINGS_UPDATED',
                    settings: { disableSelfView: false },
                });
            }
        } catch (error) {
            // The embedded UI must never interfere with conference startup.
        }
    }

    function hasActiveLocalVideo() {
        if (!selfView || !selfView.isConnected) {
            return false;
        }

        if (cameraActiveFromParent === false) {
            return false;
        }

        const tracks = previewVideo?.srcObject?.getVideoTracks?.() || [];
        return tracks.some((track) => track.enabled && track.readyState !== 'ended');
    }

    function updateSelfViewVisibility() {
        if (!selfView) {
            return;
        }
        const active = hasActiveLocalVideo();
        selfView.classList.toggle('echocall-self-view-video-active', active);
        if (active && !position) {
            window.requestAnimationFrame(placeAutomatically);
        }
    }

    function localVideoStream() {
        try {
            const localTracks = window.APP?.conference?.getLocalTracks?.() || [];
            const jitsiTrack = localTracks.find((track) => track?.getType?.() === 'video');
            const mediaTrack = jitsiTrack?.getTrack?.();
            if (mediaTrack && mediaTrack.readyState !== 'ended') {
                return new MediaStream([mediaTrack]);
            }
        } catch (error) {
            // Fall back to Jitsi's local video element below.
        }

        const candidate = document.querySelector('#localVideo_container video')
            || document.querySelector('#filmstripLocalVideo video')
            || document.querySelector('#localVideoContainer video')
            || document.getElementById('localVideo');
        sourceVideo = candidate || sourceVideo;
        return sourceVideo?.srcObject || null;
    }

    function syncPreviewStream() {
        if (!previewVideo) {
            return;
        }
        const stream = localVideoStream();
        const currentTrack = previewVideo.srcObject?.getVideoTracks?.()[0];
        const nextTrack = stream?.getVideoTracks?.()[0];
        if (currentTrack !== nextTrack) {
            previewVideo.srcObject = stream;
            previewVideo.play?.().catch?.(() => {});
        }
        updateSelfViewVisibility();
    }

    function boundsFor(element) {
        const rect = element.getBoundingClientRect();
        return {
            maxX: Math.max(sideInset, window.innerWidth - rect.width - sideInset),
            maxY: Math.max(topInset, window.innerHeight - rect.height - bottomInset),
        };
    }

    function clamp(value, minimum, maximum) {
        return Math.max(minimum, Math.min(maximum, value));
    }

    function applyPosition(x, y) {
        if (!selfView || !selfView.isConnected) {
            return;
        }
        const bounds = boundsFor(selfView);
        position = {
            x: clamp(x, sideInset, bounds.maxX),
            y: clamp(y, topInset, bounds.maxY),
        };
        selfView.style.setProperty(
            'transform',
            `translate3d(${Math.round(position.x)}px, ${Math.round(position.y)}px, 0)`,
            'important',
        );
    }

    function placeAutomatically() {
        if (!selfView) {
            return;
        }
        const rect = selfView.getBoundingClientRect();
        const x = window.innerWidth > window.innerHeight
            ? sideInset
            : window.innerWidth - rect.width - sideInset;
        applyPosition(x, topInset);
    }

    function onPointerMove(event) {
        if (!drag || event.pointerId !== drag.pointerId) {
            return;
        }
        event.preventDefault();
        applyPosition(
            drag.originX + event.clientX - drag.startX,
            drag.originY + event.clientY - drag.startY,
        );
    }

    function finishDrag(event) {
        if (!drag || event.pointerId !== drag.pointerId) {
            return;
        }
        selfView?.classList.remove('echocall-self-view-dragging');
        drag = null;
    }

    function onPointerDown(event) {
        if (!selfView || event.button > 0) {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        const current = position || { x: sideInset, y: topInset };
        drag = {
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            originX: current.x,
            originY: current.y,
        };
        selfView.classList.add('echocall-self-view-dragging');
        selfView.setPointerCapture?.(event.pointerId);
    }

    function attachSelfView() {
        if (!selfView) {
            selfView = document.createElement('div');
            selfView.id = 'echocall-self-view';
            previewVideo = document.createElement('video');
            previewVideo.autoplay = true;
            previewVideo.muted = true;
            previewVideo.playsInline = true;
            selfView.appendChild(previewVideo);
            document.body.appendChild(selfView);
            selfView.addEventListener('pointerdown', onPointerDown);
        }
        syncPreviewStream();
    }

    window.addEventListener('pointermove', onPointerMove, { passive: false });
    window.addEventListener('pointerup', finishDrag);
    window.addEventListener('pointercancel', finishDrag);
    window.addEventListener('resize', () => {
        window.requestAnimationFrame(() => {
            if (position) {
                applyPosition(position.x, position.y);
            } else {
                placeAutomatically();
            }
        });
    });
    window.addEventListener('message', (event) => {
        if (!parentOrigin || event.source !== window.parent || event.origin !== parentOrigin) {
            return;
        }
        if (event.data?.type === 'echocall:local-video-active') {
            cameraActiveFromParent = event.data.active === true;
            updateSelfViewVisibility();
        }
    });

    new MutationObserver(() => {
        attachSelfView();
    }).observe(document.documentElement, {
        childList: true,
        subtree: true,
    });
    window.setInterval(() => {
        ensureSelfViewEnabled();
        attachSelfView();
    }, 500);
    ensureSelfViewEnabled();
    attachSelfView();
})();
