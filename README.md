# learning-feeds

RSS feed for content published on LinkedIn Learning.

## Loader

Run the loader, this will pull all LinkedIn Learning Courses that are
currently published (i.e. not retired) and related Author and Skills
metadata for the Course.

```sh
CLIENT_ID=... CLIENT_SECRET=... python learning-feeds/loader/loader.py
```

## Server

Start the server:

```sh
DB_PATH=learning.db uvicorn learning-feeds.server.server:app --log-config=learning-feeds/server/log_conf.yml
```
