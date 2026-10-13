FROM docker.io/library/ruby@sha256:91627f55e8969006aab67d15c92fb930500ff73948803da1330b8a853fecebb5
# The full (buildpack-deps) variant carries the compiler and client library headers that projects' native gems
# build against during setup, plus Ruby 3.1.7, Bundler 2.3.27 and the bundled Minitest 5.15.0 the fixture locks.
# The image adds only the fixture, so the build fetches nothing.
COPY Gemfile Gemfile.lock /opt/corsair-fixture/
COPY test/ /opt/corsair-fixture/test/
ENV HOME=/tmp
USER 10001:10001
