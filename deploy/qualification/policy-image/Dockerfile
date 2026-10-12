FROM docker.io/curlimages/curl@sha256:9a1ed35addb45476afa911696297f8e115993df459278ed036182dd2cd22b67b AS curl
FROM nvcr.io/nvidia/base/ubuntu@sha256:43c1682f10cdf6561e22f6da1765d491b6f0e5808f94d5fde29d7bdbe75142d5
USER root
COPY --from=curl /usr/bin/curl /usr/bin/curl
COPY --from=curl /usr/lib /opt/corsair-curl/usr/lib
COPY --from=curl /lib /opt/corsair-curl/lib
RUN ln -s /opt/corsair-curl/lib/ld-musl-x86_64.so.1 /lib/ld-musl-x86_64.so.1 \
    && ln -sfn libcurl.so.4.8.0 /opt/corsair-curl/usr/lib/libcurl.so.4 \
    && ln -sfn libcurl.so.4 /opt/corsair-curl/usr/lib/libcurl.so \
    && printf '/opt/corsair-curl/lib:/opt/corsair-curl/usr/lib\n' > /etc/ld-musl-x86_64.path \
    && mkdir -p /opt/corsair-denied /opt/corsair-readonly \
    && printf 'corsair-readable-canary\n' > /opt/corsair-denied/readable \
    && printf 'corsair-writable-canary\n' > /opt/corsair-readonly/writable \
    && chmod 755 /opt/corsair-denied /opt/corsair-readonly \
    && chmod 444 /opt/corsair-denied/readable \
    && chmod 666 /opt/corsair-readonly/writable
USER 10001:10001
