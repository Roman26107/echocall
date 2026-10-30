# Supply a compatible Jitsi web image pinned to a tag or digest at build time.
ARG JITSI_WEB_BASE
FROM ${JITSI_WEB_BASE}

USER root
COPY echocall-embedded.css /usr/share/jitsi-meet/css/echocall-embedded.css
COPY echocall-embedded.js /usr/share/jitsi-meet/echocall-embedded.js
RUN CSS="$(tr '\n' ' ' < /usr/share/jitsi-meet/css/echocall-embedded.css)" \
    && sed -i "/<\/head>/i\\    <style id=\"echocall-embedded-ui\">${CSS}</style>" \
        /usr/share/jitsi-meet/index.html \
    && sed -i "/<\/body>/i\\    <script src=\"/libs/echocall-embedded.js\"></script>" \
        /usr/share/jitsi-meet/index.html \
    && cp /usr/share/jitsi-meet/echocall-embedded.js \
        /usr/share/jitsi-meet/libs/echocall-embedded.js
USER 1001
