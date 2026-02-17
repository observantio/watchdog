#!/bin/bash
set -e

docker compose down --volumes --remove-orphans
docker compose up -d --build

cd ui
npm install
npm run dev