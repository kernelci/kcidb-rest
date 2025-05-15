import kcidb
import tempfile
import os
import argparse
from kcidb import io, db, mq, orm, oo, monitor, tests, unittest, misc # noqa
import json
import time

# default database
DATABASE = "postgresql:dbname=kcidb user=kcidb password=kcidb host=localhost port=5432"

def get_db_credentials():
    global DATABASE
    # if PG_URI present - use it instead of default DATABASE
    pg_uri = os.environ.get("PG_URI")
    if pg_uri:
        DATABASE = pg_uri
    pgpass = os.environ.get("PG_PASS")
    if not pgpass:
        raise Exception("PG_PASS environment variable not set")
    (pgpass_fd, pgpass_filename) = tempfile.mkstemp(suffix=".pgpass")
    with os.fdopen(pgpass_fd, mode="w", encoding="utf-8") as pgpass_file:
        pgpass_file.write(pgpass)
    os.environ["PGPASSFILE"] = pgpass_filename
    db_uri = os.environ.get("PG_DSN")
    if db_uri:
        DATABASE = db_uri


def get_db_client(database):
    get_db_credentials()
    db = kcidb.db.Client(database)
    return db


def move_file_to_failed_dir(filename, failed_dir):
    try:
        os.rename(filename, os.path.join(failed_dir, os.path.basename(filename)))
    except Exception as e:
        print(f"Error moving file {filename} to failed directory: {e}")
        raise e


def ingest_submissions(spool_dir, db_client=None):
    if db_client is None:
        raise Exception("db_client is None")
    io_schema = db_client.get_schema()[1]
    # iterate over all files in the directory spool_dir
    for filename in os.listdir(spool_dir):
        # skip if not json
        if not filename.endswith(".json"):
            #print(f"Skipping invalid extension {filename}")
            continue
        print(f"Ingesting {filename}")
        try:
            with open(os.path.join(spool_dir, filename), "r") as f:
                fsize = os.path.getsize(os.path.join(spool_dir, filename))
                if fsize == 0:
                    print(f"File {filename} is empty, skipping, deleting")
                    os.remove(os.path.join(spool_dir, filename))
                    continue
                start_time = time.time()
                print(f"File size: {fsize}")
                try:
                    data = json.loads(f.read())
                    data = io_schema.validate(data)
                    data = io_schema.upgrade(data, copy=False)
                    db_client.load(data)
                except Exception as e:
                    print(f"Error loading data: {e}")
                    print(f"File: {filename}")
                    # move the file to the failed directory for later inspection
                    failed_dir = os.path.join(spool_dir, "failed")
                    move_file_to_failed_dir(os.path.join(spool_dir, filename), failed_dir)
                    continue
                ing_speed = fsize / (time.time() - start_time) / 1024
                print(f"Ingested {filename} in {ing_speed} KB/s")
                # delete the file
                os.remove(os.path.join(spool_dir, filename))
        except Exception as e:
            print(f"Error: {e}")
            print(f"File: {filename}")
            raise e


def verify_spool_dirs(spool_dir):
    if not os.path.exists(spool_dir):
        print(f"Spool directory {spool_dir} does not exist")
        raise Exception(f"Spool directory {spool_dir} does not exist")
    if not os.path.isdir(spool_dir):
        raise Exception(f"Spool directory {spool_dir} is not a directory")
    if not os.access(spool_dir, os.W_OK):
        raise Exception(f"Spool directory {spool_dir} is not writable")
    print(f"Spool directory {spool_dir} is valid and writable")
    # we need also ${spool_dir}/failed
    failed_dir = os.path.join(spool_dir, "failed")
    if not os.path.exists(failed_dir):
        print(f"Failed directory {failed_dir} does not exist, creating")
        os.makedirs(failed_dir)
    if not os.path.isdir(failed_dir):
        raise Exception(f"Failed directory {failed_dir} is not a directory")
    if not os.access(failed_dir, os.W_OK):
        raise Exception(f"Failed directory {failed_dir} is not writable")
    print(f"Failed directory {failed_dir} is valid and writable")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spool-dir", type=str, required=True)
    args = parser.parse_args()
    print("Starting ingestion process...")
    verify_spool_dirs(args.spool_dir)
    get_db_credentials()
    db_client = get_db_client(DATABASE)
    print(f"Database: {DATABASE}")
    while True:
        ingest_submissions(args.spool_dir, db_client)
        time.sleep(1)

if __name__ == "__main__":
    main()
