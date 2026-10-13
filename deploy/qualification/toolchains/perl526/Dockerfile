FROM docker.io/library/perl@sha256:c7e412792cb4f1a5b9b7a632c01a02fb469c615e6745279b4ae1821d03105bc7
# Perl 5.26.3 with its core Test::More, Test::Harness (prove) and ExtUtils::MakeMaker, and GNU Make from the
# upstream image; nothing is fetched, so the build runs with --network=none.
COPY Makefile.PL /opt/corsair-fixture/Makefile.PL
COPY lib/ /opt/corsair-fixture/lib/
COPY t/ /opt/corsair-fixture/t/
ENV HOME=/tmp
USER 10001:10001
