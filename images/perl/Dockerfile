# Digest-pinned Debian runtime with Perl, core TAP tooling and Devel::Cover.
FROM docker.io/library/debian@sha256:62bd423aeee912639ca8ee681c2b762cb3e25137e0a92b20be455898a9f034ad
RUN apt-get update && apt-get install -y --no-install-recommends \
      perl=5.40.1-6+deb13u1 cpanminus=1.7048-1 libdevel-cover-perl=1.44-1+b2 libjson-maybexs-perl=1.004008-1 && \
    perl -MDevel::Cover -MTest::More -MJSON::PP -e 'print "$Devel::Cover::VERSION\n"' && \
    rm -rf /cover_db /var/lib/apt/lists/*
RUN useradd --create-home --uid 1000 corsair
WORKDIR /work
