# KCIDB-REST

KCIDB-REST is a REST API wrapper around the KernelCI Database (KCIDB). It provides services for submitting kernel test, build, and checkout data to the KCIDB database via HTTP requests.

## Architecture

The system consists of several interconnected components:

1. **kcidb-restd-rs** - A Rust-based REST service that:
   - Receives JSON submissions via HTTP/HTTPS
   - Authenticates users via JWT
   - Stores valid submissions in a spool directory
   - Provides status endpoints for submissions

2. **ingester** - A Python service that:
   - Processes JSON submissions from the spool directory
   - Validates them against the KCIDB schema
   - Loads them into the KCIDB database
   - Archives processed submissions

3. **logspec-worker** - A Python service that:
   - Monitors the database for failed tests and builds
   - Downloads and analyzes log files using the logspec library
   - Identifies issues and incidents from logs
   - Submits findings back to KCIDB

4. **PostgreSQL Database** - Stores all KCIDB data
   - Can be run locally (self-hosted mode)
   - Can be connected to Google Cloud SQL

## Installation

### Prerequisites

Docker and Docker Compose (the newer `docker compose` plugin, not the legacy `docker-compose`; version 2.0+ required)
- Git

### Clone the Repository

```bash
git clone https://github.com/kernelci/kcidb-rest.git
cd kcidb-rest
```

### Configuration

Create a `.env` file in the root directory with the following environment variables:

```
# PostgreSQL configuration
POSTGRES_USER=kcidb
POSTGRES_PASSWORD=kcidb
POSTGRES_DB=kcidb
PG_URI=postgresql:dbname=kcidb user=kcidb_editor password=kcidb host=db port=5432

# JWT authentication
JWT_SECRET=your_jwt_secret

# Optional: SSL/TLS certificates
CERTBOT_DOMAIN=your.domain.com
CERTBOT_EMAIL=your.email@example.com
```

## Usage

### Starting the Services

#### Self-hosted Mode (with local PostgreSQL)

The self-hosted profile includes a local PostgreSQL database and an initialization service:

```bash
sudo docker compose --profile=self-hosted up -d --build
```

This command:
- Builds and starts all necessary containers
- Sets up a local PostgreSQL database
- Initializes the database schema
- Starts the REST API, ingester, and logspec-worker services

#### Google Cloud SQL Mode

If you prefer to use Google Cloud SQL as your database:

```bash
docker compose --profile=google-cloud-sql up -d --build
```

Make sure to provide the appropriate credentials in your `.env` file.

### Generating tokens

If your kcidb-rest is installed in isolated environment, you can disable JWT authentication by commenting out the JWT command in `docker-compose.yaml`:

```yaml
#    command: ["/usr/local/bin/kcidb-restd-rs","-j",""]
```

If you want to use JWT authentication, you can generate a token using the following command:

```bash
kcidb-restd-rs/tools/jwt_rest.py --secret YOUR_SECRET --origin YOUR_ORIGIN
```

### Sending Data to the API

To submit data to the REST API:

```bash
curl -X POST \
  -H "Authorization: Bearer <jwt_token>" \
  -H "Content-Type: application/json" \
  -d @submission.json \
  https://localhost:443/submit
```

### Checking Status

You can check the status of your submission using:

```bash
curl -X GET \
  -H "Authorization: Bearer <jwt_token>" \
  https://localhost:443/status/<submission_id>
```

## Directory Structure

- `/spool`: Stores incoming submissions (managed by docker volumes)
  - `/spool/failed`: Stores submissions that failed to process
  - `/spool/archive`: Stores successfully processed submissions

- `/state`: Stores application state (managed by docker volumes)
  - `processed_builds.db`: Tracks processed builds
  - `processed_tests.db`: Tracks processed tests

- `/cache`: Caches downloaded log files for logspec-worker

## Development and Debugging

### Viewing Logs

```bash
docker logs kcidb-rest
docker logs ingester
docker logs logspec-worker
docker logs postgres
```

### Connecting to the Database

```bash
docker exec -it postgres psql -U kcidb -d kcidb
```

### Authentication

The REST API uses JWT for authentication. To disable JWT authentication (not recommended for production):

Uncomment this line in docker-compose.yaml:
```yaml
#    command: ["/usr/local/bin/kcidb-restd-rs","-j",""]
```

### Manual Log Processing

To manually process a log file through logspec without submitting it to the database, you can run:

```bash
docker exec -it logspec-worker python /app/logspec_worker.py --spool-dir /app/spool --origins microsoft --dry-run
```

## License

This project is licensed under the [LGPL-2.1 license](https://www.gnu.org/licenses/old-licenses/lgpl-2.1.en.html).

