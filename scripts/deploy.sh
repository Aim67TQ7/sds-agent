#!/bin/bash
# sds-agent deployment to Maggie VPS (89.116.157.23)
set -e

VPS="root@89.116.157.23"
REMOTE_DIR="/opt/sds-agent"
WEB_DIR="/opt/sds-web"

echo "=== SDS Agent Deploy ==="

# 1. Create directories
echo "[1/8] Creating directories..."
ssh $VPS "mkdir -p $REMOTE_DIR/{backend,database,kernels/tools,kernels/tenants,scripts} $WEB_DIR"

# 2. Copy files
echo "[2/8] Copying files..."
scp docker-compose.yml $VPS:$REMOTE_DIR/
scp backend/Dockerfile backend/requirements.txt backend/main.py $VPS:$REMOTE_DIR/backend/
scp database/init.sql $VPS:$REMOTE_DIR/database/
scp kernels/sds_v1.0.ttc.md $VPS:$REMOTE_DIR/kernels/
scp kernels/tools/printerdrivers.ttc.md $VPS:$REMOTE_DIR/kernels/tools/
scp kernels/tenants/bunting-sds.ttc.md $VPS:$REMOTE_DIR/kernels/tenants/
scp scripts/add-tenant.sh $VPS:$REMOTE_DIR/scripts/

# 3. Create .env if not exists
echo "[3/8] Checking .env..."
ssh $VPS "test -f $REMOTE_DIR/.env || cat > $REMOTE_DIR/.env << 'ENVEOF'
DB_PASSWORD=$(openssl rand -hex 16)
DB_APP_PASSWORD=$(openssl rand -hex 16)
ANTHROPIC_API_KEY=CHANGE_ME
SECRET_KEY=$(openssl rand -hex 32)
ENVIRONMENT=production
ENVEOF"
echo "  -> Check $REMOTE_DIR/.env and set ANTHROPIC_API_KEY"

# 4. Start containers
echo "[4/8] Starting containers..."
ssh $VPS "cd $REMOTE_DIR && docker compose up -d --build"

# 5. Wait for postgres healthy
echo "[5/8] Waiting for postgres..."
ssh $VPS "sleep 10"

# 6. Set up restricted DB user
echo "[6/8] Setting up sds_app DB user..."
ssh $VPS "docker exec sds-postgres psql -U sds_admin -d sds_gp3 -c \"DO \\\$\\\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sds_app') THEN EXECUTE 'CREATE ROLE sds_app WITH LOGIN PASSWORD ''' || current_setting('app.db_app_password', true) || ''''; END IF; END \\\$\\\$;\"" || true

# 7. Build frontend
echo "[7/8] Building frontend..."
cd frontend && npm install && npm run build
scp -r dist/* $VPS:$WEB_DIR/
cd ..

# 8. Health check
echo "[8/8] Health check..."
ssh $VPS "curl -s http://localhost:8201/health"

echo ""
echo "=== Deploy complete ==="
echo "Next steps:"
echo "  1. Set ANTHROPIC_API_KEY in $REMOTE_DIR/.env"
echo "  2. Set DB_APP_PASSWORD in .env and update sds_app role password"
echo "  3. Add Caddy block to /opt/n0v8v/Caddyfile"
echo "  4. Register first user: curl -X POST https://sds.gp3.app/auth/register ..."
