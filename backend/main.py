from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import Response
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
import google.generativeai as genai
from pydantic import BaseModel
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import os
import re
import io
import uuid
import json
import socket

# ============================================================
# APP SETUP
# ============================================================

app = FastAPI(
    title="sds.gp3.app - SDS Management Agent",
    description="Multi-tenant SDS management powered by AI",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://sds.gp3.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# CONFIG
# ============================================================

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 7

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10)
SessionLocal = sessionmaker(bind=engine)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()
genai.configure(api_key=GEMINI_API_KEY)

# ============================================================
# MODELS
# ============================================================

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    tenant_code: str

class QuestionRequest(BaseModel):
    question: str

class DownloadRequest(BaseModel):
    evidence_type: str = "all"
    format: str = "pdf"

class ChemicalCreate(BaseModel):
    chemical_name: str
    cas_number: str = ""
    manufacturer: str = ""
    product_code: str = ""
    storage_class: str = "general_storage"
    location: str = ""
    quantity: str = ""
    unit: str = "each"
    critical: bool = False

class LabelRequest(BaseModel):
    chemical_id: str
    label_type: str = "ghs_primary"
    label_size: str = "4x6"
    quantity: int = 2

class PrintRequest(BaseModel):
    chemical_id: str
    label_type: str = "ghs_primary"
    label_size: str = "4x6"
    quantity: int = 2
    printer_ip: Optional[str] = None

# ============================================================
# DEPENDENCIES
# ============================================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return {
            "user_id": payload["user_id"],
            "tenant_id": payload["tenant_id"],
            "role": payload.get("role", "user"),
        }
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def set_tenant_context(db: Session, tenant_id: str):
    db.execute(text("SET LOCAL app.current_tenant_id = :tid"), {"tid": tenant_id})

# ============================================================
# KERNEL LOADER (3-LAYER)
# ============================================================

def load_agent_kernel(db: Session, tenant_id: str) -> str:
    """Load 3-layer kernel: agent + tool references + tenant config."""

    # Layer 1: Agent kernel
    agent_kernel_path = Path("/app/kernels/sds_v1.0.ttc.md")
    if agent_kernel_path.exists():
        agent_kernel = agent_kernel_path.read_text()
    else:
        agent_kernel = "You are an SDS management assistant."

    # Get tenant info
    result = db.execute(text(
        "SELECT company_name, tenant_slug FROM tenants WHERE id = :tid"
    ), {"tid": tenant_id})
    tenant = result.fetchone()
    tenant_name = tenant[0] if tenant else "Unknown"
    tenant_slug = tenant[1] if tenant else "unknown"

    # Get chemical registry
    result = db.execute(text("""
        SELECT chemical_name, cas_number, storage_class, location, status, critical
        FROM chemicals WHERE tenant_id = :tid ORDER BY chemical_name
    """), {"tid": tenant_id})
    chemicals = result.fetchall()

    chemical_list = "\n".join([
        f"  {ch[0]}: CAS={ch[1] or 'N/A'} | storage={ch[2]} | loc={ch[3] or 'unassigned'} | status={ch[4]} | critical={ch[5]}"
        for ch in chemicals
    ]) or "  No chemicals registered yet."

    # Inject variables
    kernel = agent_kernel.replace("{TENANT_NAME}", tenant_name)
    kernel = kernel.replace("{CHEMICAL_LIST}", chemical_list)

    # Layer 2: Resolve tool kernel references (§tools/...)
    tool_refs = re.findall(r'§tools/(\S+\.ttc\.md)', kernel)
    for tool_ref in set(tool_refs):
        tool_path = Path(f"/app/kernels/tools/{tool_ref}")
        if tool_path.exists():
            tool_content = tool_path.read_text()
            # Append tool kernel as reference section
            kernel += f"\n\n---\n\n<!-- Tool: {tool_ref} -->\n{tool_content}"

    # Layer 3: Tenant kernel
    tenant_kernel_path = Path(f"/app/kernels/tenants/{tenant_slug}-sds.ttc.md")
    if tenant_kernel_path.exists():
        tenant_kernel = tenant_kernel_path.read_text()
        tenant_kernel = tenant_kernel.replace("{TENANT_NAME}", tenant_name)
        kernel += "\n\n---\n\n" + tenant_kernel

    return kernel


def load_tenant_branding(db: Session, tenant_id: str) -> dict:
    """Parse branding from tenant kernel."""
    result = db.execute(text(
        "SELECT tenant_slug, company_name FROM tenants WHERE id = :tid"
    ), {"tid": tenant_id})
    tenant = result.fetchone()
    if not tenant:
        return {"company_name": "Unknown", "slug": "unknown"}

    slug = tenant[0]
    branding = {
        "company_name": tenant[1], "slug": slug,
        "logo_path": None, "primary_color": "#003366",
        "accent_color": "#CC0000", "font": "Helvetica",
        "address_lines": [], "phone": "", "web": "",
        "report_footer": f"Confidential — {tenant[1]}",
    }

    kernel_path = Path(f"/app/kernels/tenants/{slug}-sds.ttc.md")
    if not kernel_path.exists():
        return branding

    content = kernel_path.read_text()
    brand_match = re.search(r'### 品牌标识.*?```(.*?)```', content, re.DOTALL)
    if not brand_match:
        return branding

    for line in brand_match.group(1).strip().split("\n"):
        line = line.strip()
        if ":=" not in line:
            continue
        key, val = line.split(":=", 1)
        key, val = key.strip(), val.strip().strip('"')
        if key == "logo_file":
            p = Path(f"/app/uploads/tenants/{slug}/{val}")
            if p.exists():
                branding["logo_path"] = str(p)
        elif key == "primary_color": branding["primary_color"] = val
        elif key == "accent_color": branding["accent_color"] = val
        elif key == "font": branding["font"] = val
        elif key == "report_footer": branding["report_footer"] = val
        elif key == "phone": branding["phone"] = val
        elif key == "web": branding["web"] = val
        elif key in ("line1", "line2", "line3"):
            branding["address_lines"].append(val)

    return branding


def get_tenant_printer_config(tenant_id: str, db: Session) -> dict:
    """Read printer config from tenant kernel."""
    result = db.execute(text(
        "SELECT tenant_slug FROM tenants WHERE id = :tid"
    ), {"tid": tenant_id})
    tenant = result.fetchone()
    if not tenant:
        return {}

    kernel_path = Path(f"/app/kernels/tenants/{tenant[0]}-sds.ttc.md")
    if not kernel_path.exists():
        return {}

    content = kernel_path.read_text()
    print_match = re.search(r'### 打印配置.*?```(.*?)```', content, re.DOTALL)
    if not print_match:
        return {}

    config = {}
    for line in print_match.group(1).strip().split("\n"):
        line = line.strip()
        if ":=" not in line:
            continue
        key, val = line.split(":=", 1)
        key, val = key.strip(), val.strip().strip('"')
        config[key] = val

    return config


def call_agent(kernel: str, user_message: str, context: str = "") -> dict:
    """Call Gemini with the composed kernel."""
    messages_content = f"{context}\n\n{user_message}" if context else user_message

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=kernel,
    )

    response = model.generate_content(
        messages_content,
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=6000,
            temperature=0.2,
        ),
    )

    # Gemini usage metadata
    usage = response.usage_metadata
    input_tokens = getattr(usage, 'prompt_token_count', 0) if usage else 0
    output_tokens = getattr(usage, 'candidates_token_count', 0) if usage else 0

    return {
        "text": response.text,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def log_tokens(db: Session, tenant_id: str, user_id: str, request_type: str, agent_response: dict):
    # Gemini 2.0 Flash pricing: $0.10/1M input, $0.40/1M output
    cost = (agent_response["input_tokens"] * 0.0001 / 1000) + (agent_response["output_tokens"] * 0.0004 / 1000)
    db.execute(text("""
        INSERT INTO token_usage (tenant_id, user_id, request_type, input_tokens, output_tokens, cost)
        VALUES (:tid, :uid, :rtype, :inp, :out, :cost)
    """), {
        "tid": tenant_id, "uid": user_id, "rtype": request_type,
        "inp": agent_response["input_tokens"], "out": agent_response["output_tokens"], "cost": cost,
    })

# ============================================================
# AUTH ENDPOINTS
# ============================================================

@app.post("/auth/login")
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    result = db.execute(text("""
        SELECT u.id, u.password_hash, u.tenant_id, u.role, t.company_name
        FROM users u JOIN tenants t ON u.tenant_id = t.id
        WHERE u.email = :email
    """), {"email": req.email})
    user = result.fetchone()

    if not user or not pwd_context.verify(req.password, user[1]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    db.execute(text("UPDATE users SET last_login = NOW() WHERE id = :uid"), {"uid": user[0]})
    db.commit()

    token = jwt.encode({
        "user_id": str(user[0]), "tenant_id": str(user[2]),
        "role": user[3], "exp": datetime.utcnow() + timedelta(days=TOKEN_EXPIRE_DAYS),
    }, SECRET_KEY, algorithm=ALGORITHM)

    return {"token": token, "company_name": user[4], "role": user[3]}


@app.post("/auth/register")
async def register(req: RegisterRequest, db: Session = Depends(get_db)):
    result = db.execute(text(
        "SELECT id FROM tenants WHERE tenant_slug = :slug AND subscription_status = 'active'"
    ), {"slug": req.tenant_code})
    tenant = result.fetchone()
    if not tenant:
        raise HTTPException(status_code=404, detail="Invalid registration code")

    result = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": req.email})
    if result.fetchone():
        raise HTTPException(status_code=409, detail="Email already registered")

    password_hash = pwd_context.hash(req.password)
    db.execute(text("""
        INSERT INTO users (tenant_id, email, password_hash, name, role)
        VALUES (:tid, :email, :hash, :name, 'admin')
    """), {"tid": tenant[0], "email": req.email, "hash": password_hash, "name": req.name})
    db.commit()

    return {"status": "success", "message": "User created. Please login."}

# ============================================================
# SDS UPLOAD & PARSING
# ============================================================

@app.post("/sds/upload")
async def upload_sds(
    file: UploadFile = File(...),
    auth: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    set_tenant_context(db, auth["tenant_id"])

    # Save file
    upload_dir = Path(f"/app/uploads/{auth['tenant_id']}")
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_id = str(uuid.uuid4())
    file_path = upload_dir / f"{file_id}_{file.filename}"
    content = await file.read()
    file_path.write_bytes(content)

    # AI extraction
    kernel = load_agent_kernel(db, auth["tenant_id"])
    prompt = f"""Extract ALL 16 sections from this Safety Data Sheet.
Filename: {file.filename}
File size: {len(content)} bytes

Return ONLY a valid JSON object with this structure:
{{
    "product_name": "string",
    "cas_number": "XXXXX-XX-X or null",
    "manufacturer": "string",
    "signal_word": "Danger or Warning or null",
    "revision_date": "YYYY-MM-DD or null",
    "pictogram_codes": ["GHS01", "GHS02", ...],
    "hazard_statements": ["H226 - Flammable liquid and vapour", ...],
    "precautionary_statements": ["P210 - Keep away from heat", ...],
    "hazard_class": "primary class string",
    "sections": {{
        "1": {{"title": "Product Identification", "product_name": "...", "cas_number": "...", "manufacturer": "...", "emergency_phone": "..."}},
        "2": {{"title": "Hazard Identification", "classification": "...", "signal_word": "...", "pictograms": [...], "hazard_statements": [...], "precautionary_statements": [...]}},
        "3": {{"title": "Composition", "components": [...]}},
        "4": {{"title": "First Aid", "inhalation": "...", "skin": "...", "eyes": "...", "ingestion": "..."}},
        "5": {{"title": "Fire Fighting", "extinguishing_media": "...", "specific_hazards": "...", "firefighter_protection": "..."}},
        "6": {{"title": "Accidental Release", "personal_precautions": "...", "cleanup": "..."}},
        "7": {{"title": "Handling and Storage", "safe_handling": "...", "storage_conditions": "...", "incompatibles": "..."}},
        "8": {{"title": "Exposure Controls/PPE", "oel_values": "...", "engineering_controls": "...", "ppe": {{"eyes": "...", "skin": "...", "respiratory": "...", "hands": "..."}}}},
        "9": {{"title": "Physical/Chemical Properties", "appearance": "...", "odor": "...", "flash_point": "...", "boiling_point": "...", "ph": "..."}},
        "10": {{"title": "Stability and Reactivity", "stability": "...", "incompatible_materials": "...", "hazardous_decomposition": "..."}},
        "11": {{"title": "Toxicological Info", "routes_of_exposure": "...", "acute_toxicity": "...", "ld50": "..."}},
        "12": {{"title": "Ecological Info", "ecotoxicity": "...", "persistence": "..."}},
        "13": {{"title": "Disposal", "waste_treatment": "..."}},
        "14": {{"title": "Transport", "un_number": "...", "proper_shipping_name": "...", "hazard_class": "...", "packing_group": "..."}},
        "15": {{"title": "Regulatory", "sara_313": "...", "cercla": "..."}},
        "16": {{"title": "Other Information", "revision_date": "...", "prepared_by": "..."}}
    }}
}}"""

    agent_response = call_agent(kernel, prompt)
    log_tokens(db, auth["tenant_id"], auth["user_id"], "sds_upload", agent_response)

    # Parse response
    try:
        data = json.loads(agent_response["text"])
    except json.JSONDecodeError:
        text_resp = agent_response["text"]
        start = text_resp.find("{")
        end = text_resp.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(text_resp[start:end])
        else:
            db.commit()
            return {"status": "error", "message": "Could not parse SDS data."}

    # Find or create chemical
    chemical_id = None
    if data.get("cas_number"):
        result = db.execute(text("""
            SELECT id FROM chemicals WHERE tenant_id = :tid AND cas_number = :cas
        """), {"tid": auth["tenant_id"], "cas": data["cas_number"]})
        existing = result.fetchone()
        if existing:
            chemical_id = existing[0]

    if not chemical_id and data.get("product_name"):
        result = db.execute(text("""
            SELECT id FROM chemicals WHERE tenant_id = :tid AND chemical_name = :name
        """), {"tid": auth["tenant_id"], "name": data["product_name"]})
        existing = result.fetchone()
        if existing:
            chemical_id = existing[0]

    if not chemical_id:
        # Auto-create chemical entry
        result = db.execute(text("""
            INSERT INTO chemicals (tenant_id, chemical_name, cas_number, manufacturer, signal_word, hazard_class, has_sds, sds_revision_date, status)
            VALUES (:tid, :name, :cas, :mfr, :sw, :hc, true, :rev, 'current')
            RETURNING id
        """), {
            "tid": auth["tenant_id"],
            "name": data.get("product_name", file.filename),
            "cas": data.get("cas_number"),
            "mfr": data.get("manufacturer", ""),
            "sw": data.get("signal_word"),
            "hc": data.get("hazard_class", ""),
            "rev": data.get("revision_date"),
        })
        chemical_id = result.fetchone()[0]

    # Store SDS document
    sections = data.get("sections", {})
    sections_complete = sum(1 for v in sections.values() if v)

    result = db.execute(text("""
        INSERT INTO sds_documents (tenant_id, chemical_id, file_path, file_name, revision_date, extracted_data, sections_complete, uploaded_by)
        VALUES (:tid, :cid, :path, :fname, :rev, :edata, :sc, :uid)
        RETURNING id
    """), {
        "tid": auth["tenant_id"], "cid": chemical_id,
        "path": str(file_path), "fname": file.filename,
        "rev": data.get("revision_date"),
        "edata": json.dumps(data), "sc": sections_complete,
        "uid": auth["user_id"],
    })
    sds_doc_id = result.fetchone()[0]

    # Store individual sections
    for sec_num, sec_data in sections.items():
        if sec_data:
            db.execute(text("""
                INSERT INTO sds_sections (tenant_id, sds_document_id, section_number, section_title, content)
                VALUES (:tid, :did, :num, :title, :content)
            """), {
                "tid": auth["tenant_id"], "did": sds_doc_id,
                "num": int(sec_num),
                "title": sec_data.get("title", f"Section {sec_num}"),
                "content": json.dumps(sec_data),
            })

    # Log event
    db.execute(text("""
        INSERT INTO compliance_events (tenant_id, chemical_id, event_type, event_data, created_by)
        VALUES (:tid, :cid, 'sds_uploaded', :edata, :uid)
    """), {
        "tid": auth["tenant_id"], "cid": chemical_id,
        "edata": json.dumps({"file": file.filename, "sections_extracted": sections_complete}),
        "uid": auth["user_id"],
    })

    db.commit()

    return {
        "status": "success",
        "message": f"SDS for {data.get('product_name', 'unknown')} processed. {sections_complete}/16 sections extracted.",
        "chemical_id": str(chemical_id),
        "data": data,
    }

# ============================================================
# NATURAL LANGUAGE Q&A
# ============================================================

@app.post("/sds/question")
async def ask_question(
    req: QuestionRequest,
    auth: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    set_tenant_context(db, auth["tenant_id"])

    # Build context
    result = db.execute(text("""
        SELECT c.chemical_name, c.cas_number, c.signal_word, c.hazard_class,
               c.storage_class, c.location, c.status, c.critical,
               sd.revision_date, sd.sections_complete
        FROM chemicals c
        LEFT JOIN LATERAL (
            SELECT revision_date, sections_complete FROM sds_documents
            WHERE chemical_id = c.id ORDER BY upload_date DESC LIMIT 1
        ) sd ON true
        WHERE c.tenant_id = :tid
        ORDER BY c.chemical_name
    """), {"tid": auth["tenant_id"]})
    chemicals = result.fetchall()

    context = "Chemical inventory:\n" + "\n".join([
        f"- {c[0]} (CAS: {c[1] or 'N/A'}, Signal: {c[2] or 'None'}, Class: {c[3] or 'N/A'}, "
        f"Storage: {c[4]}, Location: {c[5] or 'unassigned'}, Status: {c[6]}, Critical: {c[7]}, "
        f"SDS Rev: {c[8] or 'N/A'}, Sections: {c[9] or 0}/16)"
        for c in chemicals
    ]) if chemicals else "No chemicals in registry yet."

    context += f"\n\nTotal chemicals: {len(chemicals)}"

    kernel = load_agent_kernel(db, auth["tenant_id"])
    agent_response = call_agent(kernel, req.question, context)
    log_tokens(db, auth["tenant_id"], auth["user_id"], "question", agent_response)
    db.commit()

    return {"status": "success", "answer": agent_response["text"]}

# ============================================================
# GHS LABEL GENERATION
# ============================================================

@app.post("/sds/label")
async def generate_label(
    req: LabelRequest,
    auth: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    set_tenant_context(db, auth["tenant_id"])

    # Get chemical + latest SDS data
    result = db.execute(text("""
        SELECT c.chemical_name, c.cas_number, c.signal_word, c.manufacturer,
               sd.extracted_data
        FROM chemicals c
        LEFT JOIN LATERAL (
            SELECT extracted_data FROM sds_documents
            WHERE chemical_id = c.id ORDER BY upload_date DESC LIMIT 1
        ) sd ON true
        WHERE c.id = :cid AND c.tenant_id = :tid
    """), {"cid": req.chemical_id, "tid": auth["tenant_id"]})
    chem = result.fetchone()

    if not chem:
        raise HTTPException(status_code=404, detail="Chemical not found")

    sds_data = json.loads(chem[4]) if chem[4] else {}

    # Build label data
    label_data = {
        "product_name": chem[0],
        "cas_number": chem[1] or "",
        "signal_word": chem[2] or sds_data.get("signal_word", ""),
        "manufacturer": chem[3] or sds_data.get("manufacturer", ""),
        "pictogram_codes": sds_data.get("pictogram_codes", []),
        "hazard_statements": sds_data.get("hazard_statements", []),
        "precautionary_statements": sds_data.get("precautionary_statements", [])[:6],
        "label_type": req.label_type,
        "label_size": req.label_size,
        "quantity": req.quantity,
        "generated_at": datetime.utcnow().isoformat(),
    }

    # Generate ZPL for Zebra printers
    zpl = generate_zpl_label(label_data) if req.label_type in ("ghs_primary", "secondary") else None

    # Store label record
    db.execute(text("""
        INSERT INTO labels (tenant_id, chemical_id, label_type, label_size, label_data, zpl_content)
        VALUES (:tid, :cid, :ltype, :lsize, :ldata, :zpl)
    """), {
        "tid": auth["tenant_id"], "cid": req.chemical_id,
        "ltype": req.label_type, "lsize": req.label_size,
        "ldata": json.dumps(label_data), "zpl": zpl,
    })

    db.execute(text("""
        INSERT INTO compliance_events (tenant_id, chemical_id, event_type, event_data, created_by)
        VALUES (:tid, :cid, 'label_generated', :edata, :uid)
    """), {
        "tid": auth["tenant_id"], "cid": req.chemical_id,
        "edata": json.dumps({"label_type": req.label_type, "quantity": req.quantity}),
        "uid": auth["user_id"],
    })
    db.commit()

    return {
        "status": "success",
        "label_data": label_data,
        "zpl": zpl,
        "message": f"Label generated for {chem[0]}",
    }


def generate_zpl_label(label_data: dict) -> str:
    """Generate ZPL II code for a GHS label."""
    name = label_data["product_name"][:40]
    signal = label_data.get("signal_word", "")
    cas = label_data.get("cas_number", "")
    hazards = " ".join(label_data.get("hazard_statements", []))[:300]
    precautions = " ".join(label_data.get("precautionary_statements", []))[:400]
    supplier = label_data.get("manufacturer", "")
    qty = label_data.get("quantity", 1)
    date = datetime.utcnow().strftime("%Y-%m-%d")

    if label_data.get("label_type") == "secondary":
        # Small 2×1 secondary container label
        return f"""^XA
^CI28
^FO10,10^A0N,28,28^FD{name}^FS
^FO10,45^A0N,22,22^FD{signal}^FS
^FO10,75^FB380,3,0,L^A0N,16,16^FD{hazards[:100]}^FS
^PQ{qty}
^XZ"""

    # Full 4×6 GHS label
    pictogram_list = ", ".join(label_data.get("pictogram_codes", []))

    return f"""^XA
^CI28
^CF0,30,30

~DGR:LABEL.GRF,0,0,
^FO40,40^A0N,50,50^FD{name}^FS

^FO40,110^GB730,55,55,B^FS
^FO50,115^FR^A0N,42,42^FD{signal}^FS

^FO40,185^A0N,20,20^FDPictograms: {pictogram_list}^FS

^FO40,220^A0N,18,18^FDHazard Statements:^FS
^FO40,245^FB730,6,0,L^A0N,18,18^FD{hazards}^FS

^FO40,400^A0N,18,18^FDPrecautionary Statements:^FS
^FO40,425^FB730,8,0,L^A0N,16,16^FD{precautions}^FS

^FO40,620^A0N,18,18^FDSupplier: {supplier}^FS
^FO40,650^A0N,16,16^FDCAS: {cas}^FS
^FO40,675^A0N,14,14^FDGenerated: {date}^FS

^PQ{qty}
^XZ"""

# ============================================================
# LABEL PRINTING
# ============================================================

@app.post("/sds/print")
async def print_label(
    req: PrintRequest,
    auth: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    set_tenant_context(db, auth["tenant_id"])

    # Get latest label for this chemical
    result = db.execute(text("""
        SELECT zpl_content, label_data FROM labels
        WHERE chemical_id = :cid AND tenant_id = :tid AND label_type = :ltype
        ORDER BY created_at DESC LIMIT 1
    """), {"cid": req.chemical_id, "tid": auth["tenant_id"], "ltype": req.label_type})
    label = result.fetchone()

    if not label or not label[0]:
        raise HTTPException(status_code=404, detail="No ZPL label found. Generate a label first.")

    # Get printer IP from request or tenant config
    printer_ip = req.printer_ip
    if not printer_ip:
        config = get_tenant_printer_config(auth["tenant_id"], db)
        printer_ip = config.get("printer_ip")

    if not printer_ip or printer_ip == "TBD":
        return {
            "status": "warning",
            "message": "No printer configured. Download ZPL manually.",
            "zpl": label[0],
        }

    # Send ZPL to Zebra printer via TCP
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((printer_ip, 9100))
        sock.sendall(label[0].encode("utf-8"))
        sock.close()

        # Update print count
        db.execute(text("""
            UPDATE labels SET print_count = print_count + :qty, last_printed = NOW()
            WHERE chemical_id = :cid AND tenant_id = :tid AND label_type = :ltype
        """), {"qty": req.quantity, "cid": req.chemical_id, "tid": auth["tenant_id"], "ltype": req.label_type})

        db.execute(text("""
            INSERT INTO compliance_events (tenant_id, chemical_id, event_type, event_data, created_by)
            VALUES (:tid, :cid, 'label_printed', :edata, :uid)
        """), {
            "tid": auth["tenant_id"], "cid": req.chemical_id,
            "edata": json.dumps({"printer": printer_ip, "quantity": req.quantity}),
            "uid": auth["user_id"],
        })
        db.commit()

        return {"status": "success", "message": f"Sent {req.quantity} labels to printer at {printer_ip}"}

    except (socket.error, socket.timeout) as e:
        return {"status": "error", "message": f"Printer connection failed: {str(e)}", "zpl": label[0]}

# ============================================================
# EMERGENCY QUICK REFERENCE
# ============================================================

@app.get("/sds/emergency/{chemical_id}")
async def emergency_reference(
    chemical_id: str,
    auth: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    set_tenant_context(db, auth["tenant_id"])

    result = db.execute(text("""
        SELECT c.chemical_name, c.cas_number, c.signal_word,
               sd.extracted_data
        FROM chemicals c
        LEFT JOIN LATERAL (
            SELECT extracted_data FROM sds_documents
            WHERE chemical_id = c.id ORDER BY upload_date DESC LIMIT 1
        ) sd ON true
        WHERE c.id = :cid AND c.tenant_id = :tid
    """), {"cid": chemical_id, "tid": auth["tenant_id"]})
    chem = result.fetchone()

    if not chem:
        raise HTTPException(status_code=404, detail="Chemical not found")

    sds_data = json.loads(chem[3]) if chem[3] else {}
    sections = sds_data.get("sections", {})

    # Direct from parsed data — no AI call needed
    return {
        "chemical_name": chem[0],
        "cas_number": chem[1],
        "signal_word": chem[2],
        "first_aid": sections.get("4", {}),
        "fire_fighting": sections.get("5", {}),
        "spill_response": sections.get("6", {}),
        "ppe": sections.get("8", {}).get("ppe", sections.get("8", {})),
        "physical_properties": sections.get("9", {}),
        "stability": sections.get("10", {}),
    }

# ============================================================
# STORAGE COMPATIBILITY
# ============================================================

@app.get("/sds/compatibility")
async def check_compatibility(
    auth: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    set_tenant_context(db, auth["tenant_id"])

    result = db.execute(text("""
        SELECT c.id, c.chemical_name, c.storage_class, c.location, c.signal_word, c.hazard_class
        FROM chemicals c
        WHERE c.tenant_id = :tid AND c.location IS NOT NULL AND c.location != ''
        ORDER BY c.location, c.chemical_name
    """), {"tid": auth["tenant_id"]})
    chemicals = result.fetchall()

    # Group by location
    locations = {}
    for c in chemicals:
        loc = c[3]
        if loc not in locations:
            locations[loc] = []
        locations[loc].append({
            "id": str(c[0]), "name": c[1], "storage_class": c[2],
            "signal_word": c[4], "hazard_class": c[5],
        })

    # Check incompatibilities
    incompatible_pairs = [
        ({"flammable_cabinet"}, {"oxidizer_cabinet"}, "Flammables + Oxidizers: fire/explosion risk"),
        ({"corrosive_cabinet"}, {"flammable_cabinet"}, "Corrosives + Flammables: reaction risk"),
    ]

    warnings = []
    for loc, chems in locations.items():
        classes_present = set(c["storage_class"] for c in chems)
        for set_a, set_b, msg in incompatible_pairs:
            if classes_present & set_a and classes_present & set_b:
                warnings.append({"location": loc, "warning": msg, "chemicals": [c["name"] for c in chems]})

    return {
        "locations": locations,
        "warnings": warnings,
        "total_chemicals": len(chemicals),
        "total_locations": len(locations),
    }

# ============================================================
# CHEMICALS MANAGEMENT
# ============================================================

@app.get("/sds/chemicals")
async def list_chemicals(
    auth: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    set_tenant_context(db, auth["tenant_id"])

    result = db.execute(text("""
        SELECT c.id, c.chemical_name, c.cas_number, c.manufacturer, c.product_code,
               c.signal_word, c.hazard_class, c.storage_class, c.location,
               c.quantity, c.unit, c.critical, c.has_sds, c.sds_revision_date,
               c.status, c.notes,
               sd.file_name AS latest_sds_file,
               sd.sections_complete
        FROM chemicals c
        LEFT JOIN LATERAL (
            SELECT file_name, sections_complete FROM sds_documents
            WHERE chemical_id = c.id ORDER BY upload_date DESC LIMIT 1
        ) sd ON true
        WHERE c.tenant_id = :tid
        ORDER BY c.chemical_name
    """), {"tid": auth["tenant_id"]})

    rows = result.fetchall()
    return {
        "chemicals": [
            {
                "id": str(r[0]), "chemical_name": r[1], "cas_number": r[2],
                "manufacturer": r[3], "product_code": r[4], "signal_word": r[5],
                "hazard_class": r[6], "storage_class": r[7], "location": r[8],
                "quantity": r[9], "unit": r[10], "critical": r[11],
                "has_sds": r[12], "sds_revision_date": str(r[13]) if r[13] else None,
                "status": r[14], "notes": r[15],
                "latest_sds_file": r[16], "sections_complete": r[17],
            }
            for r in rows
        ],
        "total": len(rows),
    }


@app.post("/sds/chemicals")
async def add_chemical(
    chem: ChemicalCreate,
    auth: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    set_tenant_context(db, auth["tenant_id"])

    db.execute(text("""
        INSERT INTO chemicals
        (tenant_id, chemical_name, cas_number, manufacturer, product_code,
         storage_class, location, quantity, unit, critical)
        VALUES (:tid, :name, :cas, :mfr, :pc, :sc, :loc, :qty, :unit, :crit)
    """), {
        "tid": auth["tenant_id"], "name": chem.chemical_name,
        "cas": chem.cas_number, "mfr": chem.manufacturer,
        "pc": chem.product_code, "sc": chem.storage_class,
        "loc": chem.location, "qty": chem.quantity,
        "unit": chem.unit, "crit": chem.critical,
    })
    db.commit()

    return {"status": "success", "message": f"Chemical {chem.chemical_name} added."}

# ============================================================
# EVIDENCE PACKAGE / DOWNLOAD
# ============================================================

@app.post("/sds/download")
async def generate_evidence(
    req: DownloadRequest,
    auth: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    set_tenant_context(db, auth["tenant_id"])

    where_clause = ""
    if req.evidence_type == "expired":
        where_clause = "AND c.status = 'expired'"
    elif req.evidence_type == "missing":
        where_clause = "AND c.has_sds = false"
    elif req.evidence_type == "current":
        where_clause = "AND c.status = 'current'"

    result = db.execute(text(f"""
        SELECT c.chemical_name, c.cas_number, c.signal_word, c.hazard_class,
               c.storage_class, c.location, c.status, c.critical, c.has_sds,
               c.sds_revision_date
        FROM chemicals c
        WHERE c.tenant_id = :tid {where_clause}
        ORDER BY c.storage_class, c.chemical_name
    """), {"tid": auth["tenant_id"]})
    records = result.fetchall()

    kernel = load_agent_kernel(db, auth["tenant_id"])
    prompt = f"""Generate an SDS compliance audit evidence summary.
Include:
- Executive summary of chemical safety program health
- SDS currency status (current vs expired vs missing)
- Storage compliance issues
- Recommendations by priority

Evidence type: {req.evidence_type}
Total chemicals: {len(records)}

Chemicals:
""" + "\n".join([
        f"- {r[0]} (CAS: {r[1] or 'N/A'}, Signal: {r[2] or 'None'}, Class: {r[3] or 'N/A'}, "
        f"Storage: {r[4]}, Location: {r[5] or 'N/A'}, Status: {r[6]}, Critical: {r[7]}, "
        f"Has SDS: {r[8]}, Rev Date: {r[9] or 'N/A'})"
        for r in records
    ])

    agent_response = call_agent(kernel, prompt)
    log_tokens(db, auth["tenant_id"], auth["user_id"], "download", agent_response)
    db.commit()

    if req.format == "pdf":
        branding = load_tenant_branding(db, auth["tenant_id"])
        pdf_bytes = generate_sds_evidence_pdf(branding, records, req.evidence_type, agent_response["text"])
        filename = f"sds_evidence_{req.evidence_type}_{datetime.utcnow().strftime('%Y%m%d')}.pdf"
        return Response(
            content=pdf_bytes, media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return {
        "status": "success",
        "package_description": agent_response["text"],
        "record_count": len(records),
        "generated_at": datetime.utcnow().isoformat(),
    }


def generate_sds_evidence_pdf(branding: dict, records: list, evidence_type: str, ai_summary: str) -> bytes:
    """Generate branded SDS compliance PDF."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.colors import HexColor
    from reportlab.lib.enums import TA_CENTER

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.75*inch, bottomMargin=0.75*inch)
    primary = HexColor(branding["primary_color"])
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("BrandTitle", parent=styles["Title"], textColor=primary, fontSize=22, spaceAfter=6))
    styles.add(ParagraphStyle("BrandSub", parent=styles["Normal"], textColor=primary, fontSize=11, spaceAfter=12))
    styles.add(ParagraphStyle("SHead", parent=styles["Heading2"], textColor=primary, fontSize=14, spaceBefore=16, spaceAfter=8))
    styles.add(ParagraphStyle("Foot", parent=styles["Normal"], textColor=HexColor("#888888"), fontSize=8, alignment=TA_CENTER))

    elements = []

    if branding.get("logo_path") and Path(branding["logo_path"]).exists():
        logo = Image(branding["logo_path"], width=2*inch, height=1*inch)
        logo.hAlign = "LEFT"
        elements.append(logo)
        elements.append(Spacer(1, 12))

    elements.append(Paragraph("SDS Compliance Evidence Package", styles["BrandTitle"]))
    elements.append(Paragraph(branding["company_name"], styles["BrandSub"]))
    for line in branding.get("address_lines", []):
        elements.append(Paragraph(line, styles["Normal"]))
    elements.append(Spacer(1, 20))

    total = len(records)
    current = sum(1 for r in records if r[6] == "current")
    expired = sum(1 for r in records if r[6] == "expired")
    missing = sum(1 for r in records if not r[8])
    compliance = f"{(current / total * 100):.1f}%" if total > 0 else "N/A"

    cover = Table([
        ["Report Type", evidence_type.replace("_", " ").title()],
        ["Generated", datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")],
        ["Total Chemicals", str(total)],
        ["SDS Compliance Rate", compliance],
        ["Current SDS", str(current)],
        ["Expired SDS", str(expired)],
        ["Missing SDS", str(missing)],
    ], colWidths=[2*inch, 3*inch])
    cover.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), primary),
        ("TEXTCOLOR", (0, 0), (0, -1), HexColor("#FFFFFF")),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#CCCCCC")),
    ]))
    elements.append(cover)
    elements.append(Spacer(1, 20))

    elements.append(Paragraph("Executive Summary", styles["SHead"]))
    for para in ai_summary.split("\n\n"):
        clean = re.sub(r'[#*]+\s*', '', para.strip())
        clean = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', clean)
        if clean:
            elements.append(Paragraph(clean, styles["Normal"]))
            elements.append(Spacer(1, 6))

    if records:
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Chemical Inventory", styles["SHead"]))
        header = ["Chemical", "CAS#", "Signal", "Hazard", "Storage", "Location", "Status"]
        table_data = [header]
        for r in records:
            table_data.append([
                str(r[0])[:25], str(r[1] or ""), str(r[2] or ""),
                str(r[3] or "")[:15], str(r[4] or ""), str(r[5] or ""),
                str(r[6] or "").replace("_", " ").title(),
            ])
        t = Table(table_data, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), primary),
            ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#FFFFFF")),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#CCCCCC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [HexColor("#FFFFFF"), HexColor("#F5F5F5")]),
        ]))
        elements.append(t)

    elements.append(Spacer(1, 30))
    elements.append(Paragraph(branding.get("report_footer", ""), styles["Foot"]))
    doc.build(elements)
    return buf.getvalue()

# ============================================================
# LOGO UPLOAD
# ============================================================

@app.post("/sds/upload-logo")
async def upload_logo(
    file: UploadFile = File(...),
    auth: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    if auth["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    result = db.execute(text("SELECT tenant_slug FROM tenants WHERE id = :tid"), {"tid": auth["tenant_id"]})
    tenant = result.fetchone()
    if not tenant:
        raise HTTPException(status_code=404)

    slug = tenant[0]
    logo_dir = Path(f"/app/uploads/tenants/{slug}")
    logo_dir.mkdir(parents=True, exist_ok=True)

    kernel_path = Path(f"/app/kernels/tenants/{slug}-sds.ttc.md")
    logo_filename = "bunting-logo.png"
    if kernel_path.exists():
        match = re.search(r'logo_file\s*:=\s*(\S+)', kernel_path.read_text())
        if match:
            logo_filename = match.group(1)

    (logo_dir / logo_filename).write_bytes(await file.read())
    return {"status": "success", "message": f"Logo uploaded as {logo_filename}"}

# ============================================================
# DASHBOARD
# ============================================================

@app.get("/sds/dashboard")
async def dashboard(
    auth: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    set_tenant_context(db, auth["tenant_id"])

    chem_count = db.execute(text(
        "SELECT COUNT(*) FROM chemicals WHERE tenant_id = :tid"
    ), {"tid": auth["tenant_id"]}).scalar()

    status_counts = db.execute(text("""
        SELECT status, COUNT(*) FROM chemicals
        WHERE tenant_id = :tid GROUP BY status
    """), {"tid": auth["tenant_id"]}).fetchall()

    hazard_counts = db.execute(text("""
        SELECT storage_class, COUNT(*) FROM chemicals
        WHERE tenant_id = :tid GROUP BY storage_class
    """), {"tid": auth["tenant_id"]}).fetchall()

    label_count = db.execute(text("""
        SELECT COUNT(*), COALESCE(SUM(print_count), 0) FROM labels
        WHERE tenant_id = :tid
    """), {"tid": auth["tenant_id"]}).fetchone()

    token_usage = db.execute(text("""
        SELECT COALESCE(SUM(input_tokens + output_tokens), 0), COALESCE(SUM(cost), 0)
        FROM token_usage WHERE tenant_id = :tid
        AND timestamp >= DATE_TRUNC('month', CURRENT_DATE)
    """), {"tid": auth["tenant_id"]}).fetchone()

    events = db.execute(text("""
        SELECT ce.event_type, ce.event_data, ce.created_at, c.chemical_name
        FROM compliance_events ce
        LEFT JOIN chemicals c ON ce.chemical_id = c.id
        WHERE ce.tenant_id = :tid
        ORDER BY ce.created_at DESC LIMIT 10
    """), {"tid": auth["tenant_id"]}).fetchall()

    return {
        "chemical_count": chem_count,
        "status_summary": {r[0]: r[1] for r in status_counts},
        "hazard_summary": {r[0]: r[1] for r in hazard_counts},
        "labels_generated": label_count[0] if label_count else 0,
        "labels_printed": label_count[1] if label_count else 0,
        "token_usage": {"tokens": token_usage[0], "cost": float(token_usage[1])},
        "recent_events": [
            {"type": r[0], "data": r[1], "timestamp": r[2].isoformat(), "chemical": r[3]}
            for r in events
        ],
    }

# ============================================================
# HEALTH
# ============================================================

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "product": "sds.gp3.app",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
    }
