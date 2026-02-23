-- ============================================================
-- sds.gp3.app — Database Schema
-- Multi-tenant SDS Management with RLS
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- TABLES
-- ============================================================

CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_slug VARCHAR(50) UNIQUE NOT NULL,
    company_name VARCHAR(200) NOT NULL,
    subscription_status VARCHAR(20) DEFAULT 'active',
    token_budget_monthly INTEGER DEFAULT 100000,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(200) NOT NULL,
    role VARCHAR(20) DEFAULT 'user',
    last_login TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE chemicals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    chemical_name VARCHAR(300) NOT NULL,
    cas_number VARCHAR(20),
    manufacturer VARCHAR(200),
    product_code VARCHAR(100),
    signal_word VARCHAR(20),  -- 'Danger' or 'Warning' or null
    hazard_class VARCHAR(50),  -- primary hazard class
    storage_class VARCHAR(50) DEFAULT 'general_storage',
    location VARCHAR(100),
    quantity VARCHAR(50),
    unit VARCHAR(20) DEFAULT 'each',
    critical BOOLEAN DEFAULT FALSE,
    has_sds BOOLEAN DEFAULT FALSE,
    sds_revision_date DATE,
    status VARCHAR(30) DEFAULT 'missing_sds',
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE sds_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    chemical_id UUID REFERENCES chemicals(id),
    file_path VARCHAR(500) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    revision_date DATE,
    upload_date TIMESTAMP DEFAULT NOW(),
    extracted_data JSONB,  -- full 16-section extraction
    sections_complete INTEGER DEFAULT 0,  -- count of non-null sections
    status VARCHAR(30) DEFAULT 'processing',  -- processing, current, expired, incomplete
    uploaded_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE sds_sections (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    sds_document_id UUID NOT NULL REFERENCES sds_documents(id) ON DELETE CASCADE,
    section_number INTEGER NOT NULL CHECK (section_number BETWEEN 1 AND 16),
    section_title VARCHAR(200) NOT NULL,
    content JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (sds_document_id, section_number)
);

CREATE TABLE labels (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    chemical_id UUID NOT NULL REFERENCES chemicals(id),
    label_type VARCHAR(30) NOT NULL DEFAULT 'ghs_primary',  -- ghs_primary, secondary, pipe_marker
    label_size VARCHAR(20) NOT NULL DEFAULT '4x6',
    label_data JSONB NOT NULL,  -- structured label content
    zpl_content TEXT,  -- generated ZPL if applicable
    pdf_path VARCHAR(500),
    print_count INTEGER DEFAULT 0,
    last_printed TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE chemical_locations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    chemical_id UUID NOT NULL REFERENCES chemicals(id),
    location_name VARCHAR(100) NOT NULL,
    storage_area VARCHAR(100),
    quantity VARCHAR(50),
    date_placed DATE DEFAULT CURRENT_DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE compliance_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    chemical_id UUID REFERENCES chemicals(id),
    event_type VARCHAR(50) NOT NULL,
    event_data JSONB,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE token_usage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    user_id UUID REFERENCES users(id),
    request_type VARCHAR(50) NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost DECIMAL(10,6) DEFAULT 0,
    timestamp TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- ROW LEVEL SECURITY
-- ============================================================

ALTER TABLE chemicals ENABLE ROW LEVEL SECURITY;
ALTER TABLE sds_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE sds_sections ENABLE ROW LEVEL SECURITY;
ALTER TABLE labels ENABLE ROW LEVEL SECURITY;
ALTER TABLE chemical_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE token_usage ENABLE ROW LEVEL SECURITY;

-- Force RLS even for table owners (critical for non-superuser app role)
ALTER TABLE chemicals FORCE ROW LEVEL SECURITY;
ALTER TABLE sds_documents FORCE ROW LEVEL SECURITY;
ALTER TABLE sds_sections FORCE ROW LEVEL SECURITY;
ALTER TABLE labels FORCE ROW LEVEL SECURITY;
ALTER TABLE chemical_locations FORCE ROW LEVEL SECURITY;
ALTER TABLE compliance_events FORCE ROW LEVEL SECURITY;
ALTER TABLE token_usage FORCE ROW LEVEL SECURITY;

-- Policies
CREATE POLICY tenant_chemicals ON chemicals
    FOR ALL USING (tenant_id::text = current_setting('app.current_tenant_id', true));

CREATE POLICY tenant_sds_documents ON sds_documents
    FOR ALL USING (tenant_id::text = current_setting('app.current_tenant_id', true));

CREATE POLICY tenant_sds_sections ON sds_sections
    FOR ALL USING (tenant_id::text = current_setting('app.current_tenant_id', true));

CREATE POLICY tenant_labels ON labels
    FOR ALL USING (tenant_id::text = current_setting('app.current_tenant_id', true));

CREATE POLICY tenant_chemical_locations ON chemical_locations
    FOR ALL USING (tenant_id::text = current_setting('app.current_tenant_id', true));

CREATE POLICY tenant_compliance_events ON compliance_events
    FOR ALL USING (tenant_id::text = current_setting('app.current_tenant_id', true));

CREATE POLICY tenant_token_usage ON token_usage
    FOR ALL USING (tenant_id::text = current_setting('app.current_tenant_id', true));

-- ============================================================
-- AUTO-STATUS TRIGGER
-- ============================================================

CREATE OR REPLACE FUNCTION update_chemical_sds_status()
RETURNS TRIGGER AS $$
BEGIN
    -- Update chemical status based on latest SDS
    IF NEW.revision_date IS NOT NULL THEN
        UPDATE chemicals SET
            has_sds = true,
            sds_revision_date = NEW.revision_date,
            status = CASE
                WHEN NEW.revision_date > CURRENT_DATE - INTERVAL '3 years' THEN 'current'
                WHEN NEW.revision_date > CURRENT_DATE - INTERVAL '3 years' - INTERVAL '90 days' THEN 'expiring_soon'
                ELSE 'expired'
            END,
            updated_at = NOW()
        WHERE id = NEW.chemical_id;
    END IF;

    -- Set document status
    IF NEW.revision_date IS NOT NULL THEN
        NEW.status = CASE
            WHEN NEW.revision_date > CURRENT_DATE - INTERVAL '3 years' THEN 'current'
            WHEN NEW.revision_date > CURRENT_DATE - INTERVAL '3 years' - INTERVAL '90 days' THEN 'expiring_soon'
            ELSE 'expired'
        END;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER sds_status_trigger
    BEFORE INSERT OR UPDATE ON sds_documents
    FOR EACH ROW EXECUTE FUNCTION update_chemical_sds_status();

-- Daily refresh function
CREATE OR REPLACE FUNCTION refresh_sds_statuses()
RETURNS void AS $$
BEGIN
    UPDATE sds_documents SET
        status = CASE
            WHEN revision_date > CURRENT_DATE - INTERVAL '3 years' THEN 'current'
            WHEN revision_date > CURRENT_DATE - INTERVAL '3 years' - INTERVAL '90 days' THEN 'expiring_soon'
            ELSE 'expired'
        END
    WHERE revision_date IS NOT NULL;

    UPDATE chemicals SET
        status = CASE
            WHEN NOT has_sds THEN 'missing_sds'
            WHEN sds_revision_date > CURRENT_DATE - INTERVAL '3 years' THEN 'current'
            WHEN sds_revision_date > CURRENT_DATE - INTERVAL '3 years' - INTERVAL '90 days' THEN 'expiring_soon'
            ELSE 'expired'
        END,
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- RESTRICTED APP USER
-- ============================================================

CREATE ROLE sds_app WITH LOGIN PASSWORD 'CHANGE_ME_ON_DEPLOY';
GRANT CONNECT ON DATABASE sds_gp3 TO sds_app;
GRANT USAGE ON SCHEMA public TO sds_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sds_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO sds_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sds_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO sds_app;

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX idx_chemicals_tenant ON chemicals(tenant_id);
CREATE INDEX idx_chemicals_cas ON chemicals(tenant_id, cas_number);
CREATE INDEX idx_chemicals_status ON chemicals(tenant_id, status);
CREATE INDEX idx_chemicals_location ON chemicals(tenant_id, location);
CREATE INDEX idx_chemicals_storage ON chemicals(tenant_id, storage_class);
CREATE INDEX idx_sds_documents_tenant ON sds_documents(tenant_id);
CREATE INDEX idx_sds_documents_chemical ON sds_documents(chemical_id);
CREATE INDEX idx_sds_sections_doc ON sds_sections(sds_document_id);
CREATE INDEX idx_labels_chemical ON labels(chemical_id);
CREATE INDEX idx_labels_tenant ON labels(tenant_id);
CREATE INDEX idx_chemical_locations_tenant ON chemical_locations(tenant_id);
CREATE INDEX idx_compliance_events_tenant ON compliance_events(tenant_id);
CREATE INDEX idx_token_usage_tenant ON token_usage(tenant_id);
CREATE INDEX idx_users_email ON users(email);

-- ============================================================
-- SEED DATA
-- ============================================================

INSERT INTO tenants (tenant_slug, company_name) VALUES ('bunting', 'Bunting Magnetics Company');
