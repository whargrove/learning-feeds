import datetime
import logging
import os
import sqlite3
import sys

import requests
from slugify import slugify

logger = logging.getLogger("loader")
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


def load() -> int:
    access_token = _get_api_access_token()
    if access_token is None:
        return 1
    logger.info("Credentials acquired!")

    # TODO Get path to database file from env
    with sqlite3.connect("learning.db") as conn:
        logger.info("Starting DDL.")
        conn.executescript(
            """
            BEGIN;
            -- Course
            CREATE TABLE IF NOT EXISTS course(
                id TEXT PRIMARY KEY,
                title TEXT,
                desc TEXT,
                url TEXT,
                thumbnail TEXT,
                language TEXT,
                published_at_time INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_course_published_at_time ON course(published_at_time);
            CREATE INDEX IF NOT EXISTS idx_course_language ON course(language);
            CREATE TABLE IF NOT EXISTS course_author(
                course_id TEXT,
                author_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_course_author_course_id ON course_author(course_id);
            CREATE INDEX IF NOT EXISTS idx_course_author_author_id ON course_author(author_id);
            CREATE TABLE IF NOT EXISTS course_skill(
                course_id TEXT,
                skill_id TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_course_skill_course_id ON course_skill(course_id);
            CREATE INDEX IF NOT EXISTS idx_course_skill_skill_id ON course_skill(skill_id);
            -- Author
            CREATE TABLE IF NOT EXISTS author(
                id TEXT PRIMARY KEY,
                name TEXT,
                slug TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_author_slug ON author(slug);
            -- Skill
            CREATE TABLE IF NOT EXISTS skill(
                id TEXT PRIMARY KEY,
                name TEXT,
                slug TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_skill_slug ON skill(slug);
            -- Meta
            CREATE TABLE IF NOT EXISTS meta(last_sync_time INTEGER);
            COMMIT;
            """
        )
        logger.info("Finished DDL.")
        # TODO Impl Delta
        return _get_and_persist_courses(access_token=access_token, conn=conn)


def _get_and_persist_courses(access_token: str, conn: sqlite3.Connection) -> int:
    url = None
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        while True:
            if url is None:
                url = _get_url()
            logger.info("Getting course data: %s", url)
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            response_json = response.json()

            courses = []
            authors = []
            skills = []
            course_author_rels = []
            course_skill_rels = []

            for data in response_json["elements"]:
                course = (
                    data["urn"],  # id
                    data["title"]["value"],  # title
                    data["details"]["description"]["value"],  # desc
                    # strip any parameters that LinkedIn Learning API adds
                    # to the URL to de-identify users.
                    data["details"]["urls"]["webLaunch"].split("?")[0],  # url
                    data["details"]["images"]["primary"],  # thumbnail
                    data["details"]["availableLocales"][0]["language"],  # language
                    data["details"]["publishedAt"],  # published_at_time
                )
                courses.append(course)
                course_authors = [
                    (
                        author["urn"],  # id
                        author["name"]["value"],  # name
                        slugify(author["name"]["value"]),  # slug
                    )
                    for author in data["details"]["contributors"]
                    if author["contributionType"] == "AUTHOR"
                ]
                for a in course_authors:
                    authors.append(a)
                    course_author_rels.append((course[0], a[0]))
                course_skills = [
                    (
                        classification["associatedClassification"]["urn"],  # id
                        classification["associatedClassification"]["name"]["value"],  # name
                        slugify(classification["associatedClassification"]["name"]["value"]),  # slug
                    )
                    for classification in data["details"]["classifications"]
                    if classification["associatedClassification"]["type"] == "SKILL"
                ]
                for s in course_skills:
                    skills.append(s)
                    course_skill_rels.append((course[0], s[0]))

            conn.executemany(
                """
                INSERT OR IGNORE INTO course VALUES(?, ?, ?, ?, ?, ?, ?)
                """, courses)
            conn.executemany(
                """
                INSERT OR IGNORE INTO author VALUES(?, ?, ?)
                """, authors)
            conn.executemany(
                """
                INSERT INTO course_author VALUES(?, ?)
                """, course_author_rels)
            conn.executemany(
                """
                INSERT OR IGNORE INTO skill VALUES(?, ?, ?)
                """, skills)
            conn.executemany(
                """
                INSERT INTO course_skill VALUES(?, ?)
                """, course_skill_rels)
            conn.commit()

            if len(response_json["elements"]) < 100:
                # this is the last page
                break
            # find the "next" page
            next = [
                link
                for link in response_json["paging"]["links"]
                if link["rel"] == "next"
            ]
            if not next:
                logger.warn("")
                break
            url = f"https://api.linkedin.com{next[0]["href"]}"
    except Exception:
        logger.exception("Error while getting course data.")
        return 1

    conn.execute("INSERT INTO meta VALUES(strftime('%s', 'now') * 1000)")
    conn.commit()
    return 0


def _get_url() -> str:
    from urllib.parse import urlencode

    query_params = {
        "q": "localeAndType",
        "assetType": "COURSE",
        # TODO Support all languages
        "sourceLocale.language": "en",
        "sourceLocale.country": "US",
        "expandDepth": 1,
        "includeRetired": "false",
        "fields": "urn,title:(value),details:(availableLocales,description,classifications,contributors,images,publishedAt,urls:(webLaunch))",
        "start": 0,
        # LinkedIn Learning API will return a 403 Forbidden error if more than 100 count is used
        "count": 100,
    }
    return f"https://api.linkedin.com/v2/learningAssets?{urlencode(query_params)}"


def _get_api_access_token() -> str | None:
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    if client_id is None or client_secret is None:
        logger.error("Did not find keys from the environment.")
        return None
    access_token_url = "https://www.linkedin.com/oauth/v2/accessToken"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = f"grant_type=client_credentials&client_id={client_id}&client_secret={client_secret}"
    logger.info("Requesting credentials from %s", access_token_url)
    try:
        response = requests.post(access_token_url, data=data, headers=headers)
        response.raise_for_status()
        return response.json()["access_token"]
    except Exception:
        logger.exception(
            "Unexpected error while requesting credentials: %s", response.json()
        )
        return None


if __name__ == "__main__":
    sys.exit(load())
