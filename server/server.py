import datetime
import logging
import os
import sys
from datetime import timezone

import aiosqlite
from fastapi import FastAPI, Response
from feedgen.feed import FeedGenerator
from feedgen.util import formatRFC2822

# TODO integrate logging with FastAPI
logger = logging.getLogger("server")
logger.setLevel(logging.INFO)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
ch.setFormatter(
    logging.Formatter(fmt="%(asctime)s %(levelname)s %(name)s - %(message)s")
)
logging.Formatter.formatTime = (
    lambda self, record, datefmt=None: datetime.datetime.fromtimestamp(
        record.created, datetime.timezone.utc
    )
    .astimezone(datetime.timezone.utc)
    .isoformat(sep="T", timespec="milliseconds")
)
logger.addHandler(ch)


app = FastAPI()


@app.get("/courses")
async def courses():
    """The main feed, returns courses ordered by most recently published."""
    db_path = os.getenv("DB_PATH")
    if db_path is None:
        logger.error("DB_PATH environment variable is not set.")
        return Response(status_code=500)
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            # TODO https://kevincox.ca/2022/05/06/rss-feed-best-practices/
            #      - implement conditional request, max published_at_time to validate
            #      - compute ETag using course.id
            #      - set cache-control to 1hour
            # TODO How many courses are published in a day? This should inform
            #      the size of the feed.
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
                GROUP BY course.id
                ORDER BY course.published_at_time DESC
                LIMIT 50;
                """
            ) as cursor:
                fg = FeedGenerator()
                fg.id("https://linkedin.com/learning")
                fg.title("LinkedIn Learning - New Courses")
                fg.link(href="https://linkedin.com/learning", rel="alternate")
                # TODO link self
                async for row in cursor:
                    fe = fg.add_entry()
                    fe.id(row["id"])
                    fe.title(row["title"])
                    authors = [{"name": a} for a in row["author_names"].split(", ")]
                    fe.author(authors)
                    fe.link(href=row["url"])
                    content = f"""
                        <img src=\"{row["thumbnail"]}\" alt=\"{row["title"]}\"/>
                        <p>{row["desc"]}</p>
                        """
                    fe.content(content=content, type="CDATA")
                    published_timestamp = formatRFC2822(
                        datetime.datetime.fromtimestamp(
                            row["published_at_time"] / 1000, tz=timezone.utc
                        )
                    )
                    fe.published(published_timestamp)
                atom_feed = fg.atom_str(pretty=True)
                return Response(content=atom_feed, media_type="application/atom+xml")
    except Exception:
        logger.exception("Unexpected error while generating feed.")
        return Response(status_code=500)


@app.get("/ruok")
async def ruok():
    return "imok"
