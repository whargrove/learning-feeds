# learning-feeds

RSS feed for content published on LinkedIn Learning.

## Docker

This will build a docker image that is ready to run the server.

It includes running the loader as part of the build. The server/runtime
image copies the sqlite database file from the loader image into
runtime image so that the database is packaged with the server.

```sh
LINKEDIN_CLIENT_ID=... LINKEDIN_CLIENT_SECRET=... \
    docker build -f Dockerfile -t learning-feeds:latest \
    --secret id=LINKEDIN_CLIENT_ID \
    --secret id=LINKEDIN_CLIENT_SECRET .
```

To run the container:

```sh
docker run --cpus 1 --memory 512m -d -p 8080:8080 --name learning-feeds learning-feeds:latest
```

## Loader

You can also run the loader directly. This is use for development of the loader.

Running the loader will pull all LinkedIn Learning Courses that are
currently published (i.e. not retired) and related Author and Skills
metadata for the Course. The content data is stored in a sqlite database
file `learning.db`.

```sh
CLIENT_ID=... CLIENT_SECRET=... python learning-feeds/loader/loader.py
```

## Server

Start the server:

```sh
DB_PATH=learning.db uvicorn learning-feeds.server.server:app --log-config=learning-feeds/server/log_conf.yml
```
