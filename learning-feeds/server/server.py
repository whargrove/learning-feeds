import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Annotated

import aiosqlite
from fastapi import FastAPI, Header, Response
from feedgen.feed import FeedGenerator

logger = logging.getLogger(__name__)


app = FastAPI()


@app.get("/courses")
async def courses(
    if_none_match: Annotated[str | None, Header()] = None,
    if_modified_since: Annotated[str | None, Header()] = None,
):
    """The main feed, returns courses ordered by most recently published."""
    db_path = os.getenv("DB_PATH")
    if db_path is None:
        logger.error("DB_PATH environment variable is not set.")
        return Response(status_code=500)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row

            headers = {"cache-control": "3600"}

            # Check if "If-Modified-Since" precondition is requested and parse the
            # header value as datetime. We'll use the datetime as a parameter to the
            # database query to retrieve only items published since this precondition.
            params = []
            if if_modified_since is not None:
                # Last-Modified is always "%a, %d %b %Y %H:%M:%S GMT"
                # c.f. https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Last-Modified
                last_modified_precondition = datetime.strptime(
                    if_modified_since, "%a, %d %b %Y %H:%M:%S GMT"
                )
                logger.debug(
                    "Precondition If-Modified-Since: %s",
                    last_modified_precondition.isoformat(),
                )
                params.append(last_modified_precondition)
            else:
                params.append(datetime.fromtimestamp(0, tz=timezone.utc))

            async with db.execute(
                """
                SELECT  course.id,
                        course.title,
                        course.desc,
                        course.url,
                        course.thumbnail,
                        course.published_at_time,
                        GROUP_CONCAT(author.name, ', ') AS author_names
                FROM course
                JOIN course_author ON course.id = course_author.course_id
                JOIN author on course_author.author_id = author.id
                WHERE course.published_at_time > ?
                GROUP BY course.id
                ORDER BY course.published_at_time DESC
                LIMIT 50;
                """,
                parameters=[
                    int(precondition.timestamp() * 1000) for precondition in params
                ],
            ) as cursor:
                fg = FeedGenerator()
                fg.id("http://learning-feeds.bxfncnf2c0d8b6av.eastus.azurecontainer.io:8080/courses")
                fg.title("LinkedIn Learning - New Courses")
                fg.link(href="https://linkedin.com/learning", rel="alternate")
                fg.link(href="http://learning-feeds.bxfncnf2c0d8b6av.eastus.azurecontainer.io:8080/courses", rel="self")
                if if_modified_since is not None and not cursor.rowcount:
                    # If-Modified-Since precondition in request, and no rows returned
                    # means we need to return a 304 Not Modified
                    return Response(
                        status_code=304,
                        headers={**headers, "last-modified": if_modified_since},
                    )

                # Don't return a 404 Not Found when there are no rows in the cursor
                # instead, return a feed with no items.

                # Create a new hasher so that we can compute an etag for this resource.
                # The etag will be used to perform weak validation to see if we need
                # to return any data in this feed request.
                etag_hasher = hashlib.md5()

                last_modified_datetime = None
                async for row in cursor:
                    # use the course ID as input to the etag for this request
                    etag_hasher.update(row["id"].encode())

                    published_at = datetime.fromtimestamp(
                        row["published_at_time"] / 1000, tz=timezone.utc
                    )
                    if not last_modified_datetime:
                        # the results are ordered by published_at desc
                        # so this is only true for the first item in the results
                        # which is defacto the "most recently published" item
                        # in this feed. We'll use this datetime as the last-modified
                        last_modified_datetime = published_at

                    fe = fg.add_entry(order="append")
                    fe.id(row["id"])
                    fe.title(row["title"])
                    authors = [{"name": a} for a in row["author_names"].split(", ")]
                    fe.author(authors)
                    fe.link(href=row["url"])
                    content = f"""
                        <img src=\"{row["thumbnail"]}\" alt=\"{row["title"]}\"/>
                        <p>{row["desc"]}</p>
                        """
                    fe.summary(summary=content, type="html")
                    fe.published(published=published_at)
                    fe.updated(updated=published_at)

                if last_modified_datetime:
                    last_modified = last_modified_datetime.strftime(
                        "%a, %d %b %Y %H:%M:%S GMT"
                    )
                else:
                    # if last_modified_datetime is None, then there were no results in the
                    # cursor, so use "now" as the last-modified.
                    last_modified = (
                        datetime.now()
                        .astimezone(tz=timezone.utc)
                        .strftime("%a, %d %b %Y %H:%M:%S GMT")
                    )

                fg.updated(last_modified)

                etag = etag_hasher.hexdigest()
                if if_none_match == etag:
                    return Response(
                        status_code=304,
                        headers={
                            **headers,
                            "etag": etag,
                            "last-modified": last_modified,
                        },
                    )

                atom_feed = fg.atom_str(pretty=True)
                return Response(
                    content=atom_feed,
                    media_type="application/atom+xml",
                    headers={**headers, "etag": etag, "last-modified": last_modified},
                )
    except Exception:
        logger.exception("Unexpected error while generating feed.")
        return Response(status_code=500)


@app.get("/ruok")
async def ruok():
    return "imok"
