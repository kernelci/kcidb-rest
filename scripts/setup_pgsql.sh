#!/bin/bash
# sudo and setup user/pass to postgres:postgres
sudo -u postgres createuser -s kcidb
sudo -u postgres dropdb kcidb
sudo -u postgres createdb -O kcidb kcidb
# set password for user kcidb
sudo -u postgres psql -c "ALTER USER kcidb WITH PASSWORD 'kcidb';"
# clean up old db kcidb
