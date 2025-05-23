#!/bin/bash
if [ ! -f .env ]; then
  echo ".env file not found!"
  exit 1
fi

# if first argument is "down" then run docker compose down
if [ "$1" == "down" ]; then
  sudo docker compose --profile=self-hosted down
  exit 0
fi

# check if JWT_SECRET=your_jwt_secret is default values, then generate new using openssl
if grep -q "JWT_SECRET=your_jwt_secret" .env; then
  echo "Generating new JWT_SECRET..."
  JWT_SECRET=$(openssl rand -hex 32)
  sed -i "s/JWT_SECRET=your_jwt_secret/JWT_SECRET=$JWT_SECRET/" .env
  echo "New JWT_SECRET generated: $JWT_SECRET"
else
  echo "JWT_SECRET already set in .env"
fi

# Remove CERTBOT_DOMAIN from .env if it exists
if grep -q "CERTBOT_DOMAIN=" .env; then
  echo "Removing CERTBOT_DOMAIN from .env..."
  sed -i '/CERTBOT_DOMAIN=/d' .env
  echo "CERTBOT_DOMAIN removed from .env"
fi

sudo docker compose --profile=self-hosted up -d --build
# is config/logspec_worker.yaml exists?
if [ ! -f config/logspec_worker.yaml ]; then
    echo "logspec_worker.yaml not found, copying example"
    cp logspec-worker/logspec_worker.yaml.example config/logspec_worker.yaml
fi

