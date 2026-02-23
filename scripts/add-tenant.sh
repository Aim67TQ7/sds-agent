#!/bin/bash
# Add a new tenant to sds-agent
# Usage: ./add-tenant.sh slug "Company Name"

SLUG=$1
NAME=$2

if [ -z "$SLUG" ] || [ -z "$NAME" ]; then
    echo "Usage: ./add-tenant.sh <slug> \"Company Name\""
    exit 1
fi

echo "Adding tenant: $NAME ($SLUG)"

docker exec sds-postgres psql -U sds_admin -d sds_gp3 -c \
    "INSERT INTO tenants (tenant_slug, company_name) VALUES ('$SLUG', '$NAME');"

echo "Tenant added. Create tenant kernel at:"
echo "  kernels/tenants/${SLUG}-sds.ttc.md"
echo ""
echo "Register admin user:"
echo "  curl -X POST https://sds.gp3.app/auth/register \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"email\":\"admin@example.com\",\"password\":\"xxx\",\"name\":\"Admin\",\"tenant_code\":\"$SLUG\"}'"
