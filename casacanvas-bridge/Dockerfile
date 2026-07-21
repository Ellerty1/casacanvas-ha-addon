# Default zu einem schlanken Alpine-Image, damit `docker build` auch außerhalb
# des HA-Supervisors (z. B. per SSH auf dem Pi) direkt funktioniert.
ARG BUILD_FROM=alpine:3.20
FROM $BUILD_FROM

ENV LANG=C.UTF-8 PYTHONUNBUFFERED=1

RUN apk add --no-cache python3 py3-pip py3-aiohttp py3-yaml \
  && python3 -m pip install --no-cache-dir --break-system-packages \
       "httpx>=0.27" "pyyaml>=6.0" "websockets>=12"

COPY run.sh /run.sh
COPY bridge /opt/bridge

RUN chmod a+x /run.sh

CMD ["/run.sh"]
