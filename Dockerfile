FROM python:alpine3.17

COPY . .

RUN pip3 install -r requirements.txt


