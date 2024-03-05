# learning-feeds

RSS feed for content published on LinkedIn Learning.

## Loader

Run the loader, this will pull all LinkedIn Learning Courses that are
currently published (i.e. not retired) and related Author and Skills
metadata for the Course.

```sh
CLIENT_ID=... CLIENT_SECRET=... python loader/loader.py
```

## Server

Start the server:

```sh
DB_PATH=learning.db uvicorn server.server:app --log-config=server/log_conf.yml
```
