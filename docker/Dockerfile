# Rename the build stage from 'base' to 'builder' for clarification and code readability
FROM python:3.11.0-slim-bullseye as builder

ENV DEBIAN_FRONTEND=noninteractive \
    WORKDIR=/consensus-specs  \
    INSTALL_CMD="apt install -y git build-essential curl"


RUN mkdir ${WORKDIR}
WORKDIR ${WORKDIR}

# Chain the commands together
RUN apt update && ${INSTALL_CMD} && rm -rf /var/lib/apt/lists/* && curl -LsSf https://astral.sh/uv/install.sh | sh

# Copy the current directory contents into the builder
COPY . .

ENV PATH="/root/.cargo/bin:${PATH}"

# Inline installation commands
RUN make preinstallation && \
    make install_test && \
    make pyspec

