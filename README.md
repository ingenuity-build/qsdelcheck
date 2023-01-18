# qsdelcheck

## Environment variables
```
QSDELCHECK_DEBUG - enables debuging; True, true, TRUE or 1 to enable.
QSDELCHECK_CHAIN - chain_id to check.
QSDELCHECK_ENV   - prod, test, dev
```

Docker:

```
docker build . -t quicksilverzone/qsdelcheck:latest
docker push quicksilverzone/qsdelcheck:latest
docker run -p 9091:9091 -e QSDELCHECK_CHAIN=stargaze-1 quicksilverzone/qsdelcheck python3 check.py
```

