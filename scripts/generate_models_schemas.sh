#!/bin/bash
# git clone ... kcidb
pip install . --break-system-packages
kcidb-schema >kcidb_schema.json
datamodel-codegen --input kcidb_schema.json  --input-file-type jsonschema --output kcidb_model.py

