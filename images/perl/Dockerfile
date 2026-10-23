# Digest-pinned Debian runtime with Perl, core TAP tooling and Devel::Cover.
FROM docker.io/library/debian@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad
COPY packages.lock /opt/corsair/packages.lock
RUN printf '%s\n' \
      'deb [check-valid-until=no signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://snapshot.debian.org/archive/debian/20261023T000000Z trixie main' \
      'deb [check-valid-until=no signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://snapshot.debian.org/archive/debian/20261023T000000Z trixie-updates main' \
      'deb [check-valid-until=no signed-by=/usr/share/keyrings/debian-archive-keyring.gpg] https://snapshot.debian.org/archive/debian-security/20261023T000000Z trixie-security main' \
      > /etc/apt/sources.list && rm -f /etc/apt/sources.list.d/debian.sources
RUN --mount=type=secret,id=proxy_ca,mode=0444 \
    if [ -f /run/secrets/proxy_ca ]; then APT_CA='-o Acquire::https::CaInfo=/run/secrets/proxy_ca'; else APT_CA=''; fi; \
    apt-get ${APT_CA} update && \
    sed '/^#/d;/^$/d' /opt/corsair/packages.lock | \
      xargs apt-get ${APT_CA} install -y --no-install-recommends && \
    perl -MDevel::Cover -MTest::More -MJSON::PP -e '$] == 5.040001 or die "unexpected Perl $]"; $Devel::Cover::VERSION eq "1.44" or die "unexpected Devel::Cover"' && \
    rm -rf /cover_db /var/lib/apt/lists/*
RUN useradd --create-home --uid 1000 corsair
WORKDIR /work
