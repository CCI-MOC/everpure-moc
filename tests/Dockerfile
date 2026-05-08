FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN git clone https://github.com/PureStorage-OpenConnect/ansible-playbook-examples.git

RUN cd ansible-playbook-examples/flashblade/pure-fb-objectstore-setup/

RUN pip3 install --upgrade pip 

COPY src/ /app/src/

