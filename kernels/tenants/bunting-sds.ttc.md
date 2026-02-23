# 租户内核 | Tenant Kernel: Bunting Magnetics — SDS
## ∀ {TENANT_NAME} · SDS代理租户配置

---

### 公司概况 | Company Profile
```
company  := Bunting Magnetics Company
industry := 磁性设备制造 · Magnetic equipment manufacturing
locations := {
  newton_hq     := "Newton, KS (HQ + Manufacturing)"
  newton_plant2 := "Newton, KS (Plant 2)"
}
ehs_contact := TBD (EHS Manager)
standards   := OSHA HazCom 2012 · ISO 14001 (if applicable)
```

---

### 化学品位置 | Chemical Locations
<!-- Populate during onboarding walk-through -->
```
storage_areas := {
  main_chem_room   → "Building 1, Room 104 — Flammable Cabinet + General"
  plating_area     → "Building 1, Plating Dept — Acids + Process Chemicals"
  maintenance_shop → "Building 2, Maintenance — Lubricants + Adhesives + Solvents"
  paint_booth      → "Building 1, Paint Area — Coatings + Thinners"
  lab              → "Building 1, QC Lab — Reagents + Standards"
  receiving_dock   → "Building 1, Receiving — Temporary Storage (max 72hr)"
}
```

---

### 打印配置 | Print Configuration
```
printer_driver := §tools/printerdrivers.ttc.md § zebra_zpl
printer_model  := Zebra ZD421
printer_ip     := TBD (configure during install)
printer_dpi    := 203
print_method   := thermal_transfer
label_stock    := {
  ghs_primary    := "4×6 polypropylene (Zebra part# 10015772)"
  secondary      := "2×1 polypropylene (Zebra part# 10015340)"
  pipe_marker    := "Custom cut — ANSI color per chemical class"
}
default_quantity := 2
```

---

### 化学品类别 | Expected Chemical Categories
```
chemical_types := {
  cutting_fluids    → 切削液 (metalworking, water-soluble + neat oils)
  adhesives         → 粘合剂 (epoxies, cyanoacrylates, threadlockers)
  solvents          → 溶剂 (acetone, IPA, MEK, mineral spirits)
  lubricants        → 润滑剂 (greases, oils, penetrants)
  paints_coatings   → 涂料 (primers, topcoats, powder coat)
  welding_supplies  → 焊接材料 (anti-spatter, flux, shielding gas)
  cleaning_agents   → 清洁剂 (degreasers, all-purpose cleaners)
  plating_chemicals → 电镀化学品 (acids, process solutions)
}
```

---

### 业务规则 | Business Rules
```
sds_update_policy   := 3 years max, or when supplier issues revision
new_chemical_flow   := Requester → EHS Review → Approve/Reject → Add to registry
emergency_contact   := EHS Manager → Plant Manager → 911
spill_kit_locations := {main_chem_room, plating_area, maintenance_shop, paint_booth}
disposal_vendor     := TBD (hazardous waste hauler)
training_frequency  := Annual HazCom refresher (OSHA requirement)
right_to_know       := All employees can access SDS via this system (OSHA 1910.1200(g))
```

---

### 品牌标识 | Branding
```
logo_file     := bunting-logo.png
primary_color := #003366
accent_color  := #CC0000
font          := Helvetica
company_address := {
  line1 := "Bunting Magnetics Company"
  line2 := "500 S. Spencer Ave."
  line3 := "Newton, KS 67114"
  phone := "(316) 284-2020"
  web   := "bfrgroup.com"
}
report_footer := "Confidential — Bunting Magnetics EHS Department"
```

---

### 术语 | Tenant Vocabulary
```
# Map internal names to standard terms
# Example: "Blue Coolant" → chemical_id "TRIM-SC620"
# Example: "The acid room" → storage_area "plating_area"
```

---

### 注意事项 | Special Notes
```
# Add Bunting-specific notes here as they arise
# Example: "Plating chemicals require additional state reporting"
# Example: "All new chemicals must have GHS labels before entering production floor"
```
