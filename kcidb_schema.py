from sqlalchemy import Column, Float, Integer, Boolean, ForeignKey, DateTime, Text, Enum, ARRAY
from sqlalchemy.types import String, VARCHAR
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base
import enum

Base = declarative_base()

# Custom Enum Types
class Status(enum.Enum):
    FAIL = 'FAIL'
    ERROR = 'ERROR'
    MISS = 'MISS'
    PASS = 'PASS'
    DONE = 'DONE'
    SKIP = 'SKIP'

class UnitPrefix(enum.Enum):
    METRIC = 'metric'
    BINARY = 'binary'

# Models
class Checkout(Base):
    __tablename__ = 'checkouts'

    _timestamp = Column(DateTime(timezone=True))
    id = Column(Text, primary_key=True)
    origin = Column(Text, nullable=False, index=True)
    tree_name = Column(Text, index=True)
    git_repository_url = Column(Text, index=True)
    git_commit_hash = Column(Text)
    git_commit_name = Column(Text)
    git_repository_branch = Column(Text, index=True)
    patchset_files = Column(JSONB)
    patchset_hash = Column(Text)
    message_id = Column(Text)
    comment = Column(Text)
    start_time = Column(DateTime(timezone=True), index=True)
    log_url = Column(Text)
    log_excerpt = Column(VARCHAR(16384))
    valid = Column(Boolean, index=True)
    misc = Column(JSONB)
    git_commit_message = Column(Text)
    git_repository_branch_tip = Column(Boolean, index=True)
    git_commit_tags = Column(ARRAY(Text), index=True)
    origin_builds_finish_time = Column(DateTime(timezone=True), index=True)
    origin_tests_finish_time = Column(DateTime(timezone=True), index=True)


class Build(Base):
    __tablename__ = 'builds'

    _timestamp = Column(DateTime(timezone=True), index=True)
    checkout_id = Column(Text, ForeignKey('checkouts.id'), nullable=False, index=True)
    id = Column(Text, primary_key=True)
    origin = Column(Text, nullable=False, index=True)
    comment = Column(Text)
    start_time = Column(DateTime(timezone=True), index=True)
    duration = Column(Float)
    architecture = Column(Text, index=True)
    command = Column(Text)
    compiler = Column(Text, index=True)
    input_files = Column(JSONB)
    output_files = Column(JSONB)
    config_name = Column(Text, index=True)
    config_url = Column(Text)
    log_url = Column(Text)
    log_excerpt = Column(VARCHAR(16384))
    misc = Column(JSONB)
    status = Column(Enum(Status), index=True)


class Test(Base):
    __tablename__ = 'tests'

    _timestamp = Column(DateTime(timezone=True), index=True)
    build_id = Column(Text, ForeignKey('builds.id'), nullable=False, index=True)
    id = Column(Text, primary_key=True)
    origin = Column(Text, nullable=False, index=True)
    environment_comment = Column(Text)
    environment_misc = Column(JSONB)
    path = Column(Text, index=True)
    comment = Column(Text)
    log_url = Column(Text)
    log_excerpt = Column(VARCHAR(16384))
    status = Column(Enum(Status), index=True)
    start_time = Column(DateTime(timezone=True), index=True)
    duration = Column(Float)
    output_files = Column(JSONB)
    misc = Column(JSONB)
    number_value = Column(Float, index=True)
    environment_compatible = Column(ARRAY(Text), index=True)
    number_prefix = Column(Enum(UnitPrefix))
    number_unit = Column(Text, index=True)


class Issue(Base):
    __tablename__ = 'issues'

    _timestamp = Column(DateTime(timezone=True), index=True)
    id = Column(Text, primary_key=True)
    version = Column(Integer, primary_key=True)
    origin = Column(Text, nullable=False, index=True)
    report_url = Column(Text, index=True)
    report_subject = Column(Text)
    culprit_code = Column(Boolean, index=True)
    culprit_tool = Column(Boolean, index=True)
    culprit_harness = Column(Boolean, index=True)
    comment = Column(Text)
    misc = Column(JSONB)


class Incident(Base):
    __tablename__ = 'incidents'

    _timestamp = Column(DateTime(timezone=True), index=True)
    id = Column(Text, primary_key=True)
    origin = Column(Text, nullable=False, index=True)
    issue_id = Column(Text, index=True, nullable=False)
    issue_version = Column(Integer, index=True, nullable=False)
    build_id = Column(Text, ForeignKey('builds.id'), index=True)
    test_id = Column(Text, ForeignKey('tests.id'), index=True)
    present = Column(Boolean, index=True)
    comment = Column(Text)
    misc = Column(JSONB)


# Custom functions
def create_functions(engine):
    """Create custom PostgreSQL functions defined in the schema."""
    from sqlalchemy.sql import text
    
    # encode_uri_component function
    encode_uri_component_sql = """
    CREATE OR REPLACE FUNCTION encode_uri_component(text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT
    AS $_$
    SELECT string_agg(
        CASE
            WHEN len_bytes > 1 OR char !~ '[0-9a-zA-Z_.!~*''()-]+' THEN
                regexp_replace(
                    encode(convert_to(char, 'utf-8')::bytea, 'hex'),
                    '(..)',
                    E'%\\1',
                    'g'
                )
            else
                char
        end,
        ''
    )
    FROM (
        SELECT char, octet_length(char) AS len_bytes
        FROM regexp_split_to_table($1, '') char
    ) AS chars;
    $_$;
    """
    
    # first_agg function
    first_agg_sql = """
    CREATE OR REPLACE FUNCTION first_agg(anyelement, anyelement) RETURNS anyelement
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    AS $_$SELECT $1$_$;
    """
    
    # format_cached_url function
    format_cached_url_sql = """
    CREATE OR REPLACE FUNCTION format_cached_url(text) RETURNS text
    LANGUAGE sql IMMUTABLE STRICT
    AS $_$
        SELECT 'https://us-central1-kernelci-production.cloudfunctions.net/kcidb_cache_redirect?' ||
               encode_uri_component($1);
    $_$;
    """
    
    # get_version function
    get_version_sql = """
    CREATE OR REPLACE FUNCTION get_version() RETURNS integer
    LANGUAGE sql IMMUTABLE
    AS $$SELECT 5001$$;
    """
    
    # last_agg function
    last_agg_sql = """
    CREATE OR REPLACE FUNCTION last_agg(anyelement, anyelement) RETURNS anyelement
    LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
    AS $_$SELECT $2$_$;
    """
    
    # first aggregate
    first_agg = """
    CREATE OR REPLACE AGGREGATE first(anyelement) (
        SFUNC = first_agg,
        STYPE = anyelement,
        PARALLEL = safe
    );
    """
    
    # last aggregate
    last_agg = """
    CREATE OR REPLACE AGGREGATE last(anyelement) (
        SFUNC = last_agg,
        STYPE = anyelement,
        PARALLEL = safe
    );
    """
    
    with engine.connect() as conn:
        conn.begin()
        conn.execute(text(encode_uri_component_sql))
        conn.execute(text(first_agg_sql))
        conn.execute(text(format_cached_url_sql))
        conn.execute(text(get_version_sql))
        conn.execute(text(last_agg_sql))
        conn.execute(text(first_agg))
        conn.execute(text(last_agg))
        conn.commit()


# Database initialization function
def init_db(engine):
    """Initialize the database with the schema and custom functions."""
    Base.metadata.create_all(engine)
    create_functions(engine)


# Example usage
if __name__ == "__main__":
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    
    # Create engine
    engine = create_engine('postgresql://kcidb:kcidb@localhost:5433/kcidb')
    # Unix socket /var/run/postgresql/.s.PGSQL.5433
    #engine = create_engine('postgresql://postgres:postgres@/kcidb')
    
    # Initialize database
    init_db(engine)
    
    # Create session
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Now you can use the session to interact with the database
    # Example: query all checkouts
    # checkouts = session.query(Checkout).all()