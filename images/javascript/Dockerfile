# The same digest-pinned Node 22 runtime as images/node22, with only its built-in test runner and coverage.
FROM docker.io/library/node@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392
RUN rm -rf /usr/local/lib/node_modules/npm \
      /usr/local/lib/node_modules/corepack \
      /opt/yarn-v1.22.22 && \
    rm -f /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
      /usr/local/bin/yarn /usr/local/bin/yarnpkg && \
    test "$(node --version)" = "v22.23.3" && \
    ! command -v npm && \
    ! command -v corepack && \
    ! command -v yarn
WORKDIR /work
