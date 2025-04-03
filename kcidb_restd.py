#!/usr/bin/env python3
"""
REST FastAPI server for KCIDB to receive data from labs
"""

from fastapi import FastAPI, HTTPException, Request
from kcidb_model import Build, Checkout, Test, Status, Kcidb, Version, Resource
from kcidb_schema import Checkout as DBCheckout, Build as DBBuild, Test as DBTest, Status as DBStatus
import uvicorn
# postgres connection
import psycopg2
from sqlalchemy import Column, Integer, String, create_engine

# /home/nuclearcat/Documents/KCIDB/code/./kcidb_rest.py:15: MovedIn20Warning: The ``declarative_base()`` function is now available as sqlalchemy.orm.declarative_base(). (deprecated since: 2.0) (Background on SQLAlchemy 2.0 at: https://sqlalche.me/e/b8d9)
from sqlalchemy.orm import sessionmaker, declarative_base
import json
import psutil
import os
import logging

app = FastAPI()

# postgres connection
engine = create_engine('postgresql://kcidb:kcidb@localhost:5432/kcidb')
Session = sessionmaker(bind=engine)

def map_pydantic_to_db_tests(test):
    # by some reason: environment doesn't map to DBTest straight
    return DBTest(
        _timestamp=test.get("field_timestamp"),
        build_id=test.get("build_id"),
        id=test.get("id"),
        origin=test.get("origin"),
        environment_comment=test.get("environment").get("comment"),
        environment_misc=test.get("environment").get("misc"),
        environment_compatible=test.get("environment").get("compatible"),
        path=test.get("path"),
        comment=test.get("comment"),
        status=test.get("status"),
        start_time=test.get("start_time"),
        duration=test.get("duration"),
        output_files=test.get("output_files"),
        misc=test.get("misc"),
        number_value=test.get("number_value"),
        number_prefix=test.get("number_prefix"),
        number_unit=test.get("number_unit"),
    )

def db_insert_items(items, mapper_func=None):
    if not items:
        return
        
    session = Session()
    try:
        for item in items:
            db_item = mapper_func(item) if mapper_func else item
            session.merge(db_item)
        session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def db_insert_checkouts(checkouts):
    db_insert_items([DBCheckout(**checkout) for checkout in checkouts])


def db_insert_builds(builds):
    db_insert_items([DBBuild(**build) for build in builds])


def db_insert_tests(tests):
    db_insert_items(tests, mapper_func=map_pydantic_to_db_tests)


def check_api_key(request: Request):
    api_key = request.headers.get("Authorization")
    if not api_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


def log_memory_usage():
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    logging.info(f"Memory usage: {memory_info.rss / 1024 / 1024:.2f} MB")


API_KEY = "your_api_key_here"
# json in body
@app.post("/submit")
async def submit(request: Request):
    """
    Submit a new Kcidb node
    Authenticated with API key in header Authorization
    """
    check_api_key(request)
    json_data = await request.json()
    log_memory_usage()
    db_insert_checkouts(json_data.get("checkouts", []))
    db_insert_builds(json_data.get("builds", []))
    db_insert_tests(json_data.get("tests", []))
    return {"message": "Kcidb node submitted"}
    
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7000)
