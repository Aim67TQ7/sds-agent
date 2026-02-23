# 打印驱动工具 | Printer Drivers Tool Kernel v1.0
## ∀ 标签打印能力 · Label Printing Capabilities

---

### 身份 | Identity
```
类型 := 工具内核 · Tool Kernel
域   := 标签打印·打印机协议·标签格式
调用 := §tools/printerdrivers.ttc.md
```

This tool kernel provides printer driver specifications, label templates, and print command generation for GHS/SDS label printing.

---

### 支持打印机 | Supported Printers

#### § zebra_zpl | Zebra ZPL 热敏打印
```
protocol    := ZPL II (Zebra Programming Language)
connection  := TCP/IP (port 9100) · USB · Bluetooth
models      := {
  ZD421   → 桌面型 desktop (4" max width, 203/300 dpi)
  ZD621   → 桌面型 desktop (4" max width, 203/300 dpi, color touch)
  ZT411   → 工业型 industrial (4" max width, 203/300/600 dpi)
  ZT421   → 工业型 industrial (6.6" max width, 203/300 dpi)
  ZQ630   → 移动型 mobile (4.4" max width, 203 dpi)
}
media_types := {
  direct_thermal → 热敏纸 (no ribbon, shorter life)
  thermal_transfer → 热转印 (ribbon required, durable)
}

commands := {
  ^XA           → 标签开始 Start label format
  ^XZ           → 标签结束 End label format
  ^FO{x},{y}    → 字段原点 Field origin (dots from top-left)
  ^A0N,{h},{w}  → 字体选择 Scalable font (N=normal, h=height, w=width)
  ^FD{data}^FS  → 字段数据 Field data + separator
  ^FB{w},{lines},{space},{justify},{hang} → 字段块 Field block (word wrap)
  ^CF0,{h},{w}  → 默认字体 Change default font
  ^BY{w},{r},{h} → 条码参数 Bar code defaults
  ^BC{o},{h},{f},{g},{e},{m} → Code 128 条码
  ^BQ{o},{model},{mag} → QR码
  ^FO{x},{y}^GFA,{bytes},{total},{rowbytes},{data} → 图形 Graphic field (ASCII hex)
  ^GB{w},{h},{t},{c},{r} → 矩形框 Graphic box
  ^FR            → 反转 Field reverse (white on black)
  ^PQ{qty},{pause},{rep},{override} → 打印数量
  ~HS            → 主机状态 Host status query
}
```

**GHS 4×6 标签模板 | GHS Label Template (4×6 inch @ 203 dpi):**
```zpl
^XA
^CI28
^CF0,30,30

~~ Product Name (large, bold) ~~
^FO40,40^A0N,50,50^FD{product_name}^FS

~~ Signal Word (red box background) ~~
^FO40,110^GB730,60,60,B^FS
^FO50,115^FR^A0N,45,45^FD{signal_word}^FS

~~ Pictogram Row (up to 4 pictograms) ~~
^FO40,190^GFA,{picto_1_data}^FS
^FO230,190^GFA,{picto_2_data}^FS
^FO420,190^GFA,{picto_3_data}^FS
^FO610,190^GFA,{picto_4_data}^FS

~~ Hazard Statements ~~
^FO40,380^FB730,8,0,L^A0N,22,22
^FD{hazard_statements_joined}^FS

~~ Precautionary Statements ~~
^FO40,580^FB730,10,0,L^A0N,18,18
^FD{precautionary_statements_joined}^FS

~~ Supplier Info ~~
^FO40,820^A0N,18,18^FD{supplier_name}^FS
^FO40,845^A0N,16,16^FD{supplier_address}^FS
^FO40,868^A0N,16,16^FD{supplier_phone}^FS

~~ QR Code (links to full SDS) ~~
^FO650,820^BQN,2,5^FDLA,{sds_url}^FS

~~ CAS Number ~~
^FO40,900^A0N,16,16^FDCAS: {cas_number}^FS

~~ Date Generated ~~
^FO500,900^A0N,16,16^FDGenerated: {date}^FS

^PQ{quantity}
^XZ
```

**二次容器标签 | Secondary Container Template (2×1 inch @ 203 dpi):**
```zpl
^XA
^CI28
^FO10,10^A0N,28,28^FD{product_name}^FS
^FO10,45^A0N,22,22^FD{signal_word}^FS
^FO10,75^FB380,3,0,L^A0N,16,16^FD{key_hazards}^FS
^FO330,10^GFA,{picto_1_small}^FS
^FO330,70^GFA,{picto_2_small}^FS
^PQ{quantity}
^XZ
```

**管道标志 | Pipe Marker Template (variable width × 1 inch):**
```zpl
^XA
^CI28
~~ ANSI/ASME A13.1 Color Coding ~~
~~ Background color set by media or ^GB fill ~~
^FO10,10^A0N,30,30^FD{chemical_name}^FS
^FO10,50^A0N,20,20^FD{flow_direction} →^FS
^FO{right_edge},10^GFA,{picto_small}^FS
^PQ{quantity}
^XZ
```

---

#### § brother_ptouch | Brother P-Touch 层压标签
```
protocol    := Brother ESC/P raster
connection  := USB · Bluetooth · WiFi
models      := {
  PT-P910BT → 桌面型 (36mm max width, 360 dpi)
  PT-E550W  → 工业手持 (24mm max width, 180 dpi)
  PT-P750W  → 桌面型 (24mm max width, 180 dpi)
}
media_types := {
  TZe_tape → 层压胶带 laminated tape (3.5mm - 36mm)
  HGe_tape → 高速胶带 high-grade tape
  HSe_tube → 热缩管 heat shrink tube
}
label_format := {
  text_only   → 产品名 + 信号词 + 关键危害
  mini_ghs    → 产品名 + 象形图 + 信号词 (24mm+ tape)
  pipe_label  → 化学品名 + 流向箭头 (per ANSI A13.1)
}
use_case := 二次容器·管道标识·小瓶标签 secondary containers, pipe marking, small vials
note := 不适合全GHS标签(尺寸限制) · Not suitable for full GHS labels due to size
```

---

#### § dymo_labelwriter | Dymo LabelWriter
```
protocol    := Dymo SDK / CUPS
connection  := USB · LAN (550 Turbo)
models      := {
  LW-550       → 桌面型 (2.3" max width, 300 dpi)
  LW-550_Turbo → 桌面型+网络 (2.3" max width, 300 dpi)
  LW-5XL       → 宽幅型 (4.16" max width, 300 dpi)
}
media_types := {
  standard     → 标准纸标签 (various sizes)
  durable      → 耐用聚丙烯 polypropylene (chemical resistant)
}
label_format := {
  address_size → 1.125×3.5" (secondary container)
  shipping     → 2.3×4" (small GHS label)
  xl_shipping  → 4×6" (full GHS label, 5XL only)
}
use_case := 办公环境·轻量标签 office environments, light-duty labeling
note := 仅LW-5XL支持全GHS标签 · Only 5XL supports full GHS labels
```

---

#### § epson_colorworks | EPSON ColorWorks 彩色标签
```
protocol    := ESC/Label · SAP integration
connection  := USB · Ethernet
models      := {
  CW-C6050A  → 4" 哑光 (1200 dpi, matte inkjet)
  CW-C6050P  → 4" 光面 (1200 dpi, glossy inkjet)
  CW-C6550A  → 8" 哑光 (1200 dpi, wide format)
  CW-C6550P  → 8" 光面 (1200 dpi, wide format)
}
media_types := {
  matte_inkjet  → 哑光喷墨标签 (various stocks)
  glossy_inkjet → 光面喷墨标签
  bs5609_part2  → 海洋化学品认证 BS5609 marine chemical certified
}
ghs_advantage := {
  full_color_pictograms → 彩色GHS象形图 (red diamond border, black symbols)
  no_pre_print_needed   → 无需预印 (prints complete label including borders)
  photo_quality         → 照片级质量
  bs5609_compliant      → 海洋运输合规 (CW-C6050A with certified media)
}
label_format := PDF → printer driver handles rasterization
use_case := 高品质GHS标签·海洋运输·合规要求最高 premium GHS labels, marine shipping, highest compliance
note := 最佳GHS标签打印方案 · Best option for full-color GHS compliant labels
```

---

#### § pdf_fallback | PDF标签生成(通用)
```
protocol    := PDF generation (ReportLab / WeasyPrint)
connection  := 无需打印机 · No printer required
output      := A4/Letter PDF with cut marks
use_case    := {
  no_label_printer → 无专用打印机时
  review_approval  → 审核批准前预览
  record_keeping   → 存档记录
  outsource_print  → 外包打印
}
label_sizes := {
  ghs_4x6  → 每页1标签 1 per page
  ghs_4x2  → 每页3标签 3 per page
  secondary_2x1 → 每页10标签 10 per page
}
```

---

### ANSI管道标识颜色 | ANSI/ASME A13.1 Pipe Marking Colors
```
pipe_colors := {
  flammable        → 黄底黑字 Yellow background, Black text
  oxidizer         → 黄底黑字 Yellow background, Black text
  toxic/corrosive  → 橙底黑字 Orange background, Black text
  water_fire       → 红底白字 Red background, White text
  compressed_air   → 蓝底白字 Blue background, White text
  user_defined_1   → 绿底白字 Green background, White text
  user_defined_2   → 棕底白字 Brown background, White text
  user_defined_3   → 紫底白字 Purple background, White text
}
```

---

### 打印机选择指南 | Printer Selection Guide
```
decision_tree := {
  需要全色GHS标签?
    YES → EPSON ColorWorks (§epson_colorworks)
    NO →
      需要耐化学品?
        YES → Zebra热转印 + 聚丙烯媒体 (§zebra_zpl, thermal_transfer)
        NO →
          标签量 > 100/天?
            YES → Zebra工业型 ZT411/ZT421 (§zebra_zpl)
            NO →
              二次容器/管道标识?
                YES → Brother P-Touch (§brother_ptouch)
                NO → Zebra桌面型 ZD421/ZD621 (§zebra_zpl)

  无打印机?
    → PDF生成 (§pdf_fallback)
}
```

---

### 约束 | Constraints
```
type := 工具内核 · 不直接回答用户 · Referenced by agent kernels only
invocation := §tools/printerdrivers.ttc.md § {section_name}
update_by := n0v8v platform team
```
