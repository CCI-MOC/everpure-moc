FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
  && apt-get install -y --no-install-recommends git ca-certificates netutils\
  && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/PureStorage-OpenConnect/ansible-playbook-examples.git

WORKDIR /app/ansible-playbook-examples/flashblade/pure-fb-objectstore-setup

RUN pip3 install --upgrade pip

WORKDIR /app
COPY src/ /app/src/

CMD ["/bin/sh", "-c", "sleep infinity"]