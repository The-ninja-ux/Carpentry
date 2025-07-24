import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.backends.backend_pdf import PdfPages
from rectpack import newPacker
from collections import defaultdict
from io import BytesIO
import base64
import tempfile
import os
from streamlit.components.v1 import html

st.set_page_config(layout="wide")
st.title("🔪 Ply Cutting Plan Generator")

st.sidebar.header("Inputs")

# === Kerf Input ===
kerf = st.sidebar.number_input("Kerf (mm)", min_value=0, max_value=10, value=3)

# === Ply Sizes by Thickness ===
def get_ply_size(thk):
    return st.sidebar.selectbox(
        f"Select Ply Size for {thk}mm",
        options=["1220x2440", "1830x2440", "1830x3050"],
        key=f"ply_{thk}"
    )

ply_sizes = {thk: get_ply_size(thk) for thk in [6, 12, 18]}

# === Input Panel Sizes ===
def get_panel_input(thk):
    return st.text_area(
        f"Paste panel sizes for {thk}mm (format: width x height, one per line)",
        key=f"input_{thk}"
    )

panel_inputs = {thk: get_panel_input(thk) for thk in [6, 12, 18]}

# === Parse Input ===
def parse_input(text):
    panels = []
    for line in text.strip().splitlines():
        try:
            w, h = map(int, line.lower().replace("mm", "").replace("×", "x").split("x"))
            panels.append((w, h))
        except:
            continue
    return panels

thickness_config = {}
for thk in [6, 12, 18]:
    size_str = ply_sizes[thk]
    ply_w, ply_h = map(int, size_str.split("x"))
    pieces = parse_input(panel_inputs[thk])
    if pieces:
        grouped = defaultdict(int)
        for w, h in pieces:
            grouped[(w, h)] += 1
        thickness_config[thk] = {
            "color": {6: "#ff6666", 12: "#66cc66", 18: "#6699ff"}[thk],
            "ply_width": ply_w,
            "ply_height": ply_h,
            "pieces": [(w, h, qty) for (w, h), qty in grouped.items()]
        }

# === Process Logic ===
temp_dir = tempfile.TemporaryDirectory()
pdf_path = os.path.join(temp_dir.name, "cutting_plan_by_thickness.pdf")
pdf = PdfPages(pdf_path)

summary = []
image_sections = []

# === Legend Page ===
fig, ax = plt.subplots(figsize=(8, 4))
ax.axis('off')
ax.set_title("Panel Thickness Legend", fontsize=14, weight='bold')

for i, (thk, cfg) in enumerate(thickness_config.items()):
    ax.add_patch(Rectangle((0.1, 0.8 - i * 0.3), 0.1, 0.1, color=cfg['color']))
    ax.text(0.25, 0.8 - i * 0.3 + 0.05, f"{thk} mm Panel", va='center', fontsize=12)

plt.tight_layout()
pdf.savefig(fig)
plt.close()

# === Loop for Each Thickness ===
for thickness, config in thickness_config.items():
    ply_width = config["ply_width"]
    ply_height = config["ply_height"]
    color = config["color"]
    pieces = config["pieces"]

    rectangles = []
    original_dims = []

    for w, h, qty in pieces:
        for _ in range(qty):
            rid = len(original_dims)
            rectangles.append((w + kerf, h + kerf, rid))
            original_dims.append((w, h))

    packer = newPacker(rotation=True)
    for w, h, rid in rectangles:
        packer.add_rect(w, h, rid)
    for _ in range(100):
        packer.add_bin(ply_width, ply_height)
    packer.pack()

    used_rects = packer.rect_list()
    sheets = defaultdict(list)
    for bin_id, x, y, w, h, rid in used_rects:
        true_w, true_h = w - kerf, h - kerf
        ow, oh = original_dims[rid]
        sheets[bin_id].append((x, y, true_w, true_h, ow, oh))

    scroll_html = ""  # HTML section for this thickness

    for sheet_id, rects in sheets.items():
        fig, ax = plt.subplots(figsize=(4, 8))
        ax.set_xlim(0, ply_width)
        ax.set_ylim(0, ply_height)
        ax.set_aspect('equal')
        ax.invert_yaxis()
        ax.set_facecolor("#f5f5f5")

        used_area = 0
        for x, y, w, h, ow, oh in rects:
            ax.add_patch(Rectangle((x, y), w, h, edgecolor='black', facecolor=color, lw=1.2))
            ax.text(x + w/2, y + h/2, f"{int(ow)}×{int(oh)}",
                    fontsize=8, ha='center', va='center',
                    bbox=dict(facecolor='white', edgecolor='none', pad=1))
            used_area += w * h

        total_area = ply_width * ply_height
        waste = total_area - used_area
        waste_percent = (waste / total_area) * 100

        fig.suptitle(f"{thickness}mm Sheet {sheet_id+1} | Waste: {waste_percent:.2f}%", fontsize=10)

        buf = BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight')
        plt.close(fig)
        img_base64 = base64.b64encode(buf.getvalue()).decode()

        scroll_html += f"""
        <div style='display:flex;margin-bottom:16px;'>
            <div style='min-width:100px;text-align:center;'>
                <img src='data:image/png;base64,{img_base64}' width='50'><br>
                Sheet {sheet_id+1}<br>
                Waste: {waste_percent:.2f}%
            </div>
            <div style='flex:1;'>
                <img class='sheet-img' src='data:image/png;base64,{img_base64}' style='width:100%;max-width:600px;'>
            </div>
        </div>
        """
        pdf.savefig(fig)

    summary.append({
        "Thickness (mm)": thickness,
        "Total Sheets": len(sheets),
        "Total Pieces": len(original_dims),
        "Approx Waste %": f"{(sum([(ply_width * ply_height - sum(w * h for _, _, w, h, *_ in s)) / (ply_width * ply_height) * 100 for s in sheets.values()]) / len(sheets)):.2f}%"
    })

    with st.container():
        st.markdown(f"### {thickness}mm Panel Sheets")
        html(scroll_html, height=600, scrolling=True)

pdf.close()

# === Summary Table ===
if summary:
    st.markdown("## 🧾 Summary")
    st.dataframe(pd.DataFrame(summary))

# === PDF Download ===
with open(pdf_path, "rb") as f:
    b64_pdf = base64.b64encode(f.read()).decode()
    href = f'<a href="data:application/octet-stream;base64,{b64_pdf}" download="cutting_plan.pdf">📥 Download Cutting Plan PDF</a>'
    st.markdown(href, unsafe_allow_html=True)

st.success("Done! Paste your panel sizes above to begin.")

# import streamlit as st
# import pandas as pd
# from rectpack import newPacker
# import matplotlib.pyplot as plt
# from matplotlib.patches import Rectangle
# from matplotlib.backends.backend_pdf import PdfPages
# from collections import defaultdict
# from io import BytesIO
# import tempfile
# import os
# import base64

# # === Streamlit Page Setup ===
# st.set_page_config(page_title="Cutting Plan Optimizer", layout="wide")
# st.title("📐 Cutting Plan Optimizer")
# st.markdown("Upload or paste panel sizes by thickness. Get optimized layouts, waste %, and downloadable PDF.")

# # === Kerf Input ===
# kerf = st.number_input("Saw Blade Thickness (Kerf) in mm", min_value=0, max_value=10, value=3)

# # === Panel Color and Ply Size Options ===
# panel_colors = {6: "#ff6666", 12: "#66cc66", 18: "#6699ff"}
# standard_ply_sizes = {
#     "8x4 ft (2440×1220)": (1220, 2440),
#     "6x3 ft (1830×915)": (915, 1830),
#     "7x3 ft (2135×915)": (915, 2135),
#     "4x4 ft (1220×1220)": (1220, 1220)
# }

# # === Helper: Parse Excel-Pasted Input ===
# def parse_excel_paste(text):
#     lines = text.strip().split("\n")
#     pieces = []
#     for line in lines:
#         try:
#             parts = [int(x.strip()) for x in line.replace("x", " ").split() if x.strip().isdigit()]
#             if len(parts) >= 2:
#                 w, h = parts[:2]
#                 pieces.append((w, h, 1))
#         except:
#             continue
#     return pieces

# # === User Inputs for Each Thickness ===
# thickness_config = {}
# st.subheader("📥 Paste Panel Sizes (Width x Height)")

# col1, col2, col3 = st.columns(3)
# for thickness, col in zip([6, 12, 18], [col1, col2, col3]):
#     with col:
#         st.markdown(f"**{thickness}mm Panel**")
#         ply_choice = st.selectbox(f"Select Ply Size for {thickness}mm", options=list(standard_ply_sizes.keys()), key=f"ply_{thickness}")
#         ply_width, ply_height = standard_ply_sizes[ply_choice]
#         user_input = st.text_area(f"Paste sizes (e.g., 560x815)", key=f"input_{thickness}", height=200)
#         parsed = parse_excel_paste(user_input)
#         if parsed:
#             thickness_config[thickness] = {
#                 "color": panel_colors[thickness],
#                 "ply_width": ply_width,
#                 "ply_height": ply_height,
#                 "pieces": parsed
#             }

# if not thickness_config:
#     st.warning("Please enter panel sizes for at least one thickness.")
#     st.stop()

# # === Output Setup ===
# results_summary = []
# image_buffers = []
# temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
# pdf = PdfPages(temp_pdf.name)

# # === Add Legend Page ===
# fig, ax = plt.subplots(figsize=(8, 3))
# ax.axis('off')
# ax.set_title("Panel Thickness Legend", fontsize=14, weight='bold')
# for i, (thk, cfg) in enumerate(thickness_config.items()):
#     ax.add_patch(Rectangle((0.1, 0.8 - i * 0.3), 0.1, 0.1, color=cfg['color']))
#     ax.text(0.25, 0.8 - i * 0.3 + 0.05, f"{thk} mm Panel", va='center', fontsize=12)
# pdf.savefig(fig)
# plt.close(fig)

# # === Packing and Visualization ===
# for thickness, config in thickness_config.items():
#     ply_width = config["ply_width"]
#     ply_height = config["ply_height"]
#     color = config["color"]
#     pieces = config["pieces"]

#     rectangles = []
#     original_dims = []
#     for w, h, qty in pieces:
#         for _ in range(qty):
#             rid = len(original_dims)
#             rectangles.append((w + kerf, h + kerf, rid))
#             original_dims.append((w, h))

#     packer = newPacker(rotation=True)
#     for w, h, rid in rectangles:
#         packer.add_rect(w, h, rid)
#     for _ in range(100):
#         packer.add_bin(ply_width, ply_height)
#     packer.pack()

#     used_rects = packer.rect_list()
#     sheets = defaultdict(list)
#     for bin_id, x, y, w, h, rid in used_rects:
#         true_w, true_h = w - kerf, h - kerf
#         ow, oh = original_dims[rid]
#         sheets[bin_id].append((x, y, true_w, true_h, ow, oh))

#     total_sheets = len(sheets)
#     total_area = ply_width * ply_height

#     for sheet_id, rects in sheets.items():
#         fig, ax = plt.subplots(figsize=(6, 10))
#         ax.set_xlim(0, ply_width)
#         ax.set_ylim(0, ply_height)
#         ax.set_aspect('equal')
#         ax.invert_yaxis()
#         ax.set_facecolor("#f5f5f5")

#         used_area = 0
#         for x, y, w, h, ow, oh in rects:
#             ax.add_patch(Rectangle((x, y), w, h, edgecolor='black', facecolor=color, lw=1.5))
#             ax.text(x + w / 2, y + h / 2, f"{int(ow)}×{int(oh)}",
#                     fontsize=8, ha='center', va='center',
#                     bbox=dict(facecolor='white', edgecolor='none', pad=1))
#             used_area += w * h

#         waste = total_area - used_area
#         waste_percent = (waste / total_area) * 100

#         ax.set_title(f"{thickness}mm Panel — Sheet {sheet_id + 1} | Waste: {int(waste)} mm² ({waste_percent:.2f}%)",
#                      fontsize=10, fontweight='bold')
#         plt.tight_layout()

#         buf = BytesIO()
#         fig.savefig(buf, format='png')
#         pdf.savefig(fig)
#         plt.close(fig)
#         buf.seek(0)
#         image_buffers.append((thickness, sheet_id + 1, waste_percent, buf))

#     results_summary.append({
#         "Thickness (mm)": thickness,
#         "Total Sheets": total_sheets,
#         "Total Pieces": len(original_dims),
#         "Approx Waste %": f"{waste_percent:.2f}"
#     })

# pdf.close()

# # === Results ===
# st.subheader("📊 Cutting Summary")
# st.table(pd.DataFrame(results_summary))

# st.subheader("📸 Cutting Layouts")

# # Group images by thickness
# grouped_images = defaultdict(list)
# for thickness, sheet_id, waste_percent, buf in image_buffers:
#     grouped_images[thickness].append((sheet_id, waste_percent, buf))

# # Show scrollable rows with images side-by-side
# scroll_style = """
# <style>
# .scroll-wrapper {
#     display: flex;
#     overflow-x: auto;
#     padding: 1rem 0;
# }
# .scroll-wrapper > div {
#     margin-right: 16px;
#     text-align: center;
# }
# img.sheet-img {
#     width: 300px;
#     border: 1px solid #ccc;
# }
# </style>
# """
# st.markdown(scroll_style, unsafe_allow_html=True)

# for thickness in sorted(grouped_images.keys()):
#     st.markdown(f"**{thickness}mm Panel Sheets**")
#     scroll_html = '<div class="scroll-wrapper">'
#     for sheet_id, waste_percent, buf in grouped_images[thickness]:
#         encoded = base64.b64encode(buf.getvalue()).decode()
#         scroll_html += f'''
#             <div>
#                 <img class="sheet-img" src="data:image/png;base64,{encoded}" />
#                 <div style="font-size: 12px; margin-top: 4px;">
#                     Sheet {sheet_id} | Waste: {waste_percent:.2f}%
#                 </div>
#             </div>
#         '''
#     scroll_html += '</div>'
#     st.markdown(scroll_html, unsafe_allow_html=True)

# st.subheader("📥 Download PDF")
# st.download_button("Download Cutting Plan PDF", data=open(temp_pdf.name, "rb"), file_name="cutting_plan.pdf")
