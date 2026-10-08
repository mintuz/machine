# Disposable Ubuntu 24.04 aarch64 machine for validating install.sh and
# mise bootstrap. It mirrors a fresh headless server: one non-root user with
# passwordless sudo, no Homebrew, no mise, no build tools. Nothing from the
# host is mounted; copy the committed repository in with `docker cp`.
#
#   docker build -t mdms-ubuntu -f tests/containers/ubuntu.Dockerfile tests/containers
#   docker run -d --name mdms-ubuntu-<phase> mdms-ubuntu sleep infinity
#   git archive --format=tar HEAD | docker cp - mdms-ubuntu-<phase>:/home/dev/mac-dev-machine-setup
#   docker exec -u root mdms-ubuntu-<phase> chown -R dev:dev /home/dev/mac-dev-machine-setup
#   docker exec -u dev -w /home/dev/mac-dev-machine-setup mdms-ubuntu-<phase> ./install.sh personal
FROM ubuntu:24.04
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends sudo ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m -s /bin/bash dev \
 && echo 'dev ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/dev \
 && chmod 0440 /etc/sudoers.d/dev \
 && mkdir -p /home/dev/mac-dev-machine-setup \
 && chown dev:dev /home/dev/mac-dev-machine-setup
USER dev
WORKDIR /home/dev
ENV HOME=/home/dev
CMD ["sleep", "infinity"]
