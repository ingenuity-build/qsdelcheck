FROM python:3.12-alpine3.18

WORKDIR /root

COPY . .

RUN pip3 install -r requirements.txt


