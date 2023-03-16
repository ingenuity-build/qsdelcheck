FROM python:alpine3.17

WORKDIR /root

COPY . .

RUN pip3 install -r requirements.txt


