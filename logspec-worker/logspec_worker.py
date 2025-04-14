#!/usr/bin/env python3
"""
Search kcidb tests for unprocessed tests and process them over logspec, update entries
"""

import os
import sys
import json
# postgres
import psycopg2
from psycopg2 import sql
from psycopg2.extras import DictCursor
import datetime
import shelve
import gzip
# md5
import hashlib
import requests
from logspec_api import generate_issues_and_incidents


def set_test_processed(cursor, test_id):
    """
    Mark the test as processed in the shelve database
    """
    # shelve database
    with shelve.open("processed_tests.db") as db:
        if test_id not in db:
            db[test_id] = True
            print(f"Test {test_id} marked as processed")
        else:
            print(f"Test {test_id} already processed")


def is_test_processed(test_id):
    """
    Check if the test is already processed
    """
    with shelve.open("processed_tests.db") as db:
        if test_id in db:
            return True
        else:
            return False


def get_db_connection():
    """
    Connect to the PostgreSQL database
    """
    #pg_dsn = "postgresql://kcidb:kcidb@localhost:5432/kcidb"
    # check .pg_dsn file
    pg_dsn = None
    if os.path.exists(".pg_dsn"):
        with open(".pg_dsn", "r") as f:
            pg_dsn = f.read().strip()

    # Check if the environment variable is set
    if pg_dsn is None:
        pg_dsn = os.environ.get("PG_DSN")
        if pg_dsn is None:
            print("No database connection string found. Please set the PG_DSN environment variable or create a .pg_dsn file.")
            sys.exit(1)
    
    try:
        conn = psycopg2.connect(
            dsn=pg_dsn,
            cursor_factory=DictCursor
        )
        print("Connected to database")
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)

def get_unprocessed_tests(cursor):
    """
    Get unprocessed tests from the database
    """
    # last 24h
    last_24h = datetime.datetime.now() - datetime.timedelta(days=1)
    # 
    try:
        cursor.execute("SELECT * FROM tests WHERE _timestamp > %s AND log_url IS NOT NULL"\
        " AND status != 'PASS'", (last_24h,))
        tests = cursor.fetchall()
        return tests
    except Exception as e:
        print(f"Error fetching unprocessed tests: {e}")
        return []

def fetch_log_id(log_url):
    # generate ID as hash of URL
    log_id = hashlib.md5(log_url.encode()).hexdigest()
    # check if log_id exists in cache
    cache_file = os.path.join("cache", log_id)
    if os.path.exists(cache_file):
        return log_id
    # fetch log from URL
    try:
        response = requests.get(log_url)
        if response.status_code == 200:
            # save log to cache
            with open(cache_file, "wb") as f:
                f.write(response.content)
            print(f"Log {log_id} fetched and saved to cache")
            # decompress log if gzipped
            if log_url.endswith(".gz"):
                # rename to .gz
                os.rename(cache_file, cache_file + ".gz")
                with gzip.open(cache_file + ".gz", "rb") as f_in:
                    with open(cache_file, "wb") as f_out:
                        f_out.write(f_in.read())
                os.remove(cache_file + ".gz")                
            return log_id
        else:
            print(f"Error fetching log {log_url}: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error fetching log {log_url}: {e}")
        return None


def logspec_process_test(test):
    """
    Process the test over logspec
    """
    log_url = test['log_url']
    log_id = fetch_log_id(log_url)
    print(f"Log ID: {log_id}")
    # check if log_id is None
    if log_id is None:
        print(f"Error fetching log {log_url}")
        return
    log_file = os.path.join("cache", log_id)
    parsed_node_id = test['id']
    test_type = 'boot'
    return generate_issues_and_incidents(log_id, log_file, test_type)


def main():
    """
    Main function to process the logspec
    """
    # verify if cache directory exists
    if not os.path.exists("cache"):
        os.makedirs("cache")
    # verify if processed_tests.db exists
    if not os.path.exists("processed_tests.db"):
        with shelve.open("processed_tests.db") as db:
            db["processed_tests"] = {}

    # Connect to the database
    conn = get_db_connection()
    cursor = conn.cursor()

    # code to get unprocessed tests
    unprocessed_tests = get_unprocessed_tests(cursor)
    if not unprocessed_tests:
        print("No unprocessed tests found")
        return
    # print the unprocessed tests
    for test in unprocessed_tests:
        # print formatted column names and values
        for column, value in test.items():
            print(f"{column}: {value}")
        # Check if the test is already processed
        if is_test_processed(test['id']):
            print(f"Test {test['id']} already processed")
            continue
        # Process the test
        print(f"Processing test {test['id']}")
        # Call logspec
        result = logspec_process_test(test)
        print(f"Logspec result: {result}")



        print("\n")

    conn.close()
    cursor.close()

if __name__ == "__main__":
    main()
