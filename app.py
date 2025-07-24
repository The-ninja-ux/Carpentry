import streamlit as st
import pandas as pd
from rectpack import newPacker
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from matplotlib.backends.backend_pdf import PdfPages
from collections import defaultdict
from io import BytesIO
import tempfile
import os

# === Streamlit Page Setup ===
st.set_page_config(page_title="Cutting Plan Optimizer", layout="wide")
st.title("📐 Cutting Plan Optimizer")
st.markdown("Upload or paste panel sizes by thickness. Get optimized layouts, waste %, and downloadable PDF.")

# === Kerf Input ===
kerf = st.number_input("Saw Blade Thickness (Kerf) in mm", min_value=0, max_value=10, value=3)

# === Panel Color and Ply Size Options ===
panel_colors = {6: "#ff6666", 12: "#66cc66", 18: "#6699ff"}
standard_ply_sizes = {
    "8x4 ft (2440×1220)": (1220, 2440),
    "6x3 ft (1830×915)": (915, 1830),
    "7x3 ft (2135×915)": (915, 2135),
    "4x4 ft (1220×1220)": (1220, 1220)
}

# === Helper: Parse Excel-Pasted Input ===
def parse_excel_paste(text):
    lines = text.strip().split("\n")
    pieces = []
    for line in lines:
        try:
            parts = [int(x.strip()) for x in line.replace("x", " ").split() if x.strip().isdigit()]
            if len(parts) >= 2:
                w, h = parts[:2]
                pieces.append((w, h, 1))
        except:
            continue
    return pieces

# === User Inputs for Each Thickness ===
thickness_config = {}
st.subheader("📥 Paste Panel Sizes (Width x Height)")

col1, col2, col3 = st.columns(3)
for thickness, col in zip([6, 12, 18], [col1, col2, col3]):
    with col:
        st.markdown(f"**{thickness}mm Panel**")
        ply_choice = st.selectbox(f"Select Ply Size for {thickness}mm", options=list(standard_ply_sizes.keys()), key=f"ply_{thickness}")
        ply_width, ply_height = standard_ply_sizes[ply_choice]
        user_input = st.text_area(f"Paste sizes (e.g., 560x815)", key=f"input_{thickness}", height=200)
        parsed = parse_excel_paste(user_input)
        if parsed:
            thickness_config[thickness] = {
                "color": panel_colors[thickness],
                "ply_width": ply_width,
                "ply_height": ply_height,
                "pieces": parsed
            }

if not thickness_config:
    st.warning("Please enter panel sizes for at least one thickness.")
    st.stop()

# === Output Setup ===
results_summary = []
image_buffers = []
temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
pdf = PdfPages(temp_pdf.name)

# === Add Legend Page ===
fig, ax = plt.subplots(figsize=(8, 3))
ax.axis('off')
ax.set_title("Panel Thickness Legend", fontsize=14, weight='bold')
for i, (thk, cfg) in enumerate(thickness_config.items()):
    ax.add_patch(Rectangle((0.1, 0.8 - i * 0.3), 0.1, 0.1, color=cfg['color']))
    ax.text(0.25, 0.8 - i * 0.3 + 0.05, f"{thk} mm Panel", va='center', fontsize=12)
pdf.savefig(fig)
plt.close(fig)

# === Packing and Visualization ===
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

    total_sheets = len(sheets)
    total_area = ply_width * ply_height

    for sheet_id, rects in sheets.items():
        fig, ax = plt.subplots(figsize=(6, 10))
        ax.set_xlim(0, ply_width)
        ax.set_ylim(0, ply_height)
        ax.set_aspect('equal')
        ax.invert_yaxis()
        ax.set_facecolor("#f5f5f5")

        used_area = 0
        for x, y, w, h, ow, oh in rects:
            ax.add_patch(Rectangle((x, y), w, h, edgecolor='black', facecolor=color, lw=1.5))
            ax.text(x + w / 2, y + h / 2, f"{int(ow)}×{int(oh)}",
                    fontsize=8, ha='center', va='center',
                    bbox=dict(facecolor='white', edgecolor='none', pad=1))
            used_area += w * h

        waste = total_area - used_area
        waste_percent = (waste / total_area) * 100

        ax.set_title(f"{thickness}mm Panel — Sheet {sheet_id + 1} | Waste: {int(waste)} mm² ({waste_percent:.2f}%)",
                     fontsize=10, fontweight='bold')
        plt.tight_layout()

        buf = BytesIO()
        fig.savefig(buf, format='png')
        pdf.savefig(fig)
        plt.close(fig)
        buf.seek(0)
        image_buffers.append((thickness, sheet_id + 1, waste_percent, buf))

    results_summary.append({
        "Thickness (mm)": thickness,
        "Total Sheets": total_sheets,
        "Total Pieces": len(original_dims),
        "Approx Waste %": f"{(sum([(ply_width * ply_height - sum(w * h for x, y, w, h, _, _ in rects)) for rects in sheets.values()]) / (ply_width * ply_height * len(sheets)) * 100):.2f}" if sheets else "0.00"
    })

pdf.close()

# === Results ===
st.subheader("📊 Cutting Summary")
st.table(pd.DataFrame(results_summary))

st.subheader("📸 Cutting Layouts")
for thickness, sheet_id, waste_percent, buf in image_buffers:
    # Inside your image rendering loop:
    caption = f"{thickness}mm Panel — Sheet {sheet_id} | Waste: {waste_percent:.2f}%"
    st.image(buf, caption=caption, width=600)


st.subheader("📥 Download PDF")
st.download_button("Download Cutting Plan PDF", data=open(temp_pdf.name, "rb"), file_name="cutting_plan.pdf")
