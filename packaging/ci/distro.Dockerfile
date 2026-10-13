# A distribution image with systemd as PID 1, used by the setup integration test.
# Only what is needed to boot and to run Python is installed; curl, nftables and the
# rest are left for the setup to install, as on a fresh system.
ARG IMAGE
FROM ${IMAGE}
ARG PREP
RUN sh -c "$PREP"
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
