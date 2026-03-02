import json
import xml.etree.ElementTree as ET

def generate_from_json(json_filepath, output_filepath):
    # 1. Load the Data
    with open(json_filepath, 'r') as f:
        config = json.load(f)

    # --- VALIDATION GATE ---
    trunk_fps = config["trunk"]["total_fps"]
    for bu in config["branches"]:
        for drop in bu["drops"]:
            start_fp, end_fp = drop["fp_range"]
            if end_fp > trunk_fps:
                raise ValueError(f"Constraint Error: {bu['id']} attempts to drop FP {end_fp}, but trunk only has {trunk_fps} FPs.")

    # 2. Setup Draw.io Canvas
    mxfile = ET.Element('mxfile', version="21.6.8")
    diagram = ET.SubElement(mxfile, 'diagram', id="subsea_topo", name=config.get("system_name", "Topology"))
    mxGraphModel = ET.SubElement(diagram, 'mxGraphModel', dx="1400", dy="800", grid="1", gridSize="10", guides="1", tooltips="1", connect="1", arrows="1", fold="1", page="1", pageScale="1", pageWidth="1169", pageHeight="827", math="0", shadow="0")
    root = ET.SubElement(mxGraphModel, 'root')
    ET.SubElement(root, 'mxCell', id="0")
    ET.SubElement(root, 'mxCell', id="1", parent="0")

    # 3. Grid Constants
    FP_SPACING = 15
    NODE_WIDTH = 200 # Widened to fit multiple parallel WSS bundles
    NODE_HEIGHT = max(420, (trunk_fps * FP_SPACING) + 60)
    LANE_WIDTH = 250
    DROP_DEPTH = 150

    nodes = {}

    # --- HELPER FUNCTIONS ---
    def add_node(node_id, x, y, label):
        style = "rounded=1;whiteSpace=wrap;html=1;verticalAlign=top;spacingTop=10;fillColor=#f5f5f5;strokeColor=#666666;"
        cell = ET.SubElement(root, 'mxCell', id=node_id, value=label, style=style, vertex="1", parent="1")
        ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y), width=str(NODE_WIDTH), height=str(NODE_HEIGHT), **{'as': 'geometry'})

    def add_line(line_id, start_x, start_y, end_x, end_y):
        style = "endArrow=none;html=1;rounded=0;strokeColor=#0050ef;"
        cell = ET.SubElement(root, 'mxCell', id=line_id, style=style, edge="1", parent="1")
        geometry = ET.SubElement(cell, 'mxGeometry', relative="1", **{'as': 'geometry'})
        ET.SubElement(geometry, 'mxPoint', x=str(start_x), y=str(start_y), **{'as': 'sourcePoint'})
        ET.SubElement(geometry, 'mxPoint', x=str(end_x), y=str(end_y), **{'as': 'targetPoint'})

    def add_label(text, x, y):
        style = "text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontSize=9;"
        cell = ET.SubElement(root, 'mxCell', value=str(text), style=style, vertex="1", parent="1")
        ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y - 7), width=str(20), height=str(15), **{'as': 'geometry'})

    # --- DYNAMIC GRID PLACEMENT ---
    nodes["WEST"] = {"x": 50, "y": 50, "label": config["trunk"]["west_node"]}
    current_col_x = 50 + NODE_WIDTH + LANE_WIDTH

    for bu in config["branches"]:
        nodes[bu["id"]] = {"x": current_col_x, "y": 50, "label": bu["label"]}
        tier_y_base = 50 + NODE_HEIGHT + DROP_DEPTH

        for drop_idx, drop in enumerate(bu["drops"]):
            # Cascading Y-coordinates for multiple drops
            current_drop_y = tier_y_base + (drop_idx * (NODE_HEIGHT + DROP_DEPTH))
            nodes[drop["target_id"]] = {"x": current_col_x, "y": current_drop_y, "label": drop["label"]}

            for sub in drop.get("sub_branches", []):
                if sub.get("direction") == "east":
                    sub_x = current_col_x + NODE_WIDTH + (LANE_WIDTH * 0.75)
                    nodes[sub["target_id"]] = {"x": sub_x, "y": current_drop_y, "label": sub["label"]}
                else:
                    sub_y = current_drop_y + NODE_HEIGHT + DROP_DEPTH
                    nodes[sub["target_id"]] = {"x": current_col_x, "y": sub_y, "label": sub["label"]}

        current_col_x += NODE_WIDTH + LANE_WIDTH

    nodes["EAST"] = {"x": current_col_x, "y": 50, "label": config["trunk"]["east_node"]}

    # --- RENDER NODES ---
    for key, data in nodes.items():
        add_node(key, data["x"], data["y"], data["label"])

    # --- RENDER ROUTING ---
    for i in range(1, trunk_fps + 1):
        y_offset = nodes["WEST"]["y"] + (i * FP_SPACING) + 30
        add_line(f"fp_{i}_trunk", nodes["WEST"]["x"] + NODE_WIDTH, y_offset, nodes["EAST"]["x"], y_offset)
        add_label(i, nodes["WEST"]["x"] + NODE_WIDTH - 20, y_offset)
        add_label(i, nodes["EAST"]["x"] + 10, y_offset)

    for bu in config["branches"]:
        # Track the horizontal shift needed to prevent bundle collisions
        bundle_shift_x = 0 
        
        for drop_idx, drop in enumerate(bu["drops"]):
            start_fp, end_fp = drop["fp_range"]
            
            for i in range(start_fp, end_fp + 1):
                trunk_y = nodes["WEST"]["y"] + (i * FP_SPACING) + 30
                drop_stagger = nodes[bu["id"]]["x"] + bundle_shift_x + (i - start_fp) * 6 + 10
                
                if not drop.get("sub_branches"):
                    terminal_y = nodes[drop["target_id"]]["y"] + ((i - start_fp) * FP_SPACING) + 30
                    add_line(f"fp_{i}_{bu['id']}_{drop['target_id']}", drop_stagger, trunk_y, drop_stagger, terminal_y)
                else:
                    sub_bu_y = nodes[drop["target_id"]]["y"] + ((i - start_fp) * FP_SPACING) + 30
                    add_line(f"fp_{i}_main_to_sub", drop_stagger, trunk_y, drop_stagger, sub_bu_y)
                    
                    for sub in drop["sub_branches"]:
                        if sub["fp_range"][0] <= i <= sub["fp_range"][1]:
                            if sub.get("direction") == "east":
                                target_wall_x = nodes[sub["target_id"]]["x"]
                                add_line(f"fp_{i}_sub_east", drop_stagger, sub_bu_y, target_wall_x, sub_bu_y)
                            else:
                                terminal_y = nodes[sub["target_id"]]["y"] + ((i - sub["fp_range"][0]) * FP_SPACING) + 30
                                add_line(f"fp_{i}_sub_down", drop_stagger, sub_bu_y, drop_stagger, terminal_y)
            
            # Increase the horizontal shift for the NEXT drop bundle so they don't overlap
            bundle_width = (end_fp - start_fp + 1) * 6
            bundle_shift_x += bundle_width + 15 # 15px gap between different bundles

    # --- OUTPUT ---
    tree = ET.ElementTree(mxfile)
    ET.indent(tree, space="\t", level=0)
    tree.write(output_filepath, encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    generate_from_json("temp_payload.json", "output_topology.drawio")