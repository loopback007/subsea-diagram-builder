import json
import xml.etree.ElementTree as ET
import io


def get_ranges(obj):
    """
    Normalise both the new fp_ranges (list of pairs) and the legacy fp_range
    (single pair) schema into a consistent list of [start, end] pairs.
    Used everywhere so the rest of the engine never has to branch on schema version.
    """
    if obj.get("fp_ranges"):
        return obj["fp_ranges"]
    if obj.get("fp_range"):
        return [obj["fp_range"]]
    return []


def generate_from_config(config):
    """
    Core generation function. Accepts a config dict and returns the diagram
    as XML bytes. No file I/O — fully in-memory.
    """

    # --- VALIDATION GATE ---
    trunk_fps = config["trunk"]["total_fps"]
    seen_target_ids = set()

    for bu in config["branches"]:
        for drop in bu["drops"]:
            # Duplicate target_id check — two nodes with the same ID would silently
            # overwrite each other in the diagram dict.
            tid = drop.get("target_id", "")
            if tid in seen_target_ids:
                raise ValueError(
                    f"Duplicate target_id '{tid}' found in BU '{bu['id']}'. "
                    f"Every drop and sub-branch must have a unique ID."
                )
            seen_target_ids.add(tid)

            for r in get_ranges(drop):
                start, end = r
                if start < 1:
                    raise ValueError(
                        f"BU '{bu['id']}' drop to '{tid}': FP range start ({start}) "
                        f"must be >= 1."
                    )
                if start > end:
                    raise ValueError(
                        f"BU '{bu['id']}' drop to '{tid}': FP range [{start}, {end}] "
                        f"is inverted — start must be <= end."
                    )
                if end > trunk_fps:
                    raise ValueError(
                        f"BU '{bu['id']}' drop to '{tid}' references FP {end}, "
                        f"but trunk only has {trunk_fps} FPs."
                    )

            for sub in drop.get("sub_branches", []):
                sub_tid = sub.get("target_id", "")
                if sub_tid in seen_target_ids:
                    raise ValueError(
                        f"Duplicate target_id '{sub_tid}' found in sub-branch under "
                        f"BU '{bu['id']}' / drop '{tid}'. Every node must have a unique ID."
                    )
                seen_target_ids.add(sub_tid)

                for r in get_ranges(sub):
                    start, end = r
                    if start < 1:
                        raise ValueError(
                            f"Sub-branch '{sub_tid}' under '{tid}': FP range start "
                            f"({start}) must be >= 1."
                        )
                    if start > end:
                        raise ValueError(
                            f"Sub-branch '{sub_tid}' under '{tid}': FP range "
                            f"[{start}, {end}] is inverted — start must be <= end."
                        )
                    if end > trunk_fps:
                        raise ValueError(
                            f"Sub-branch '{sub_tid}' under '{tid}' references FP {end}, "
                            f"but trunk only has {trunk_fps} FPs."
                        )

    # --- XML SCAFFOLD ---
    mxfile = ET.Element('mxfile', version="21.6.8")
    diagram = ET.SubElement(mxfile, 'diagram', id="subsea_topo", name=config.get("system_name", "Topology"))
    mxGraphModel = ET.SubElement(
        diagram, 'mxGraphModel',
        dx="1400", dy="800", grid="1", gridSize="10", guides="1",
        tooltips="1", connect="1", arrows="1", fold="1", page="1",
        pageScale="1", pageWidth="1169", pageHeight="827", math="0", shadow="0"
    )
    root = ET.SubElement(mxGraphModel, 'root')
    ET.SubElement(root, 'mxCell', id="0")
    ET.SubElement(root, 'mxCell', id="1", parent="0")

    FP_SPACING = 20
    NODE_WIDTH = 250
    TRUNK_NODE_HEIGHT = max(420, (trunk_fps * FP_SPACING) + 60)
    LANE_WIDTH = 250
    DROP_DEPTH = 150
    nodes = {}

    # --- COLOR MAPPING ---
    fp_colors = {i: "#0050ef" for i in range(1, trunk_fps + 1)}
    for rule in config["trunk"].get("colors", []):
        start_fp, end_fp = rule["fp_range"]
        color_hex = rule["color"]
        for i in range(max(1, start_fp), min(trunk_fps, end_fp) + 1):
            fp_colors[i] = color_hex

    # --- HELPERS ---
    def add_node(node_id, x, y, label, height=TRUNK_NODE_HEIGHT):
        style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#f5f5f5;strokeColor=#666666;"
        cell = ET.SubElement(root, 'mxCell', id=node_id, value=label, style=style, vertex="1", parent="1")
        ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y), width=str(NODE_WIDTH), height=str(height), **{'as': 'geometry'})

    def add_line(line_id, start_x, start_y, end_x, end_y, color):
        style = f"endArrow=none;html=1;rounded=0;strokeColor={color};"
        cell = ET.SubElement(root, 'mxCell', id=line_id, style=style, edge="1", parent="1")
        geometry = ET.SubElement(cell, 'mxGeometry', relative="1", **{'as': 'geometry'})
        ET.SubElement(geometry, 'mxPoint', x=str(start_x), y=str(start_y), **{'as': 'sourcePoint'})
        ET.SubElement(geometry, 'mxPoint', x=str(end_x), y=str(end_y), **{'as': 'targetPoint'})

    def add_dot(dot_id, x, y, color):
        style = f"ellipse;whiteSpace=wrap;html=1;aspect=fixed;fillColor={color};strokeColor=none;perimeter=none;"
        cell = ET.SubElement(root, 'mxCell', id=dot_id, value="", style=style, vertex="1", parent="1")
        ET.SubElement(cell, 'mxGeometry', x=str(x-3), y=str(y-3), width="6", height="6", **{'as': 'geometry'})

    def add_label(text, x, y):
        style = "text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontSize=9;"
        cell = ET.SubElement(root, 'mxCell', value=str(text), style=style, vertex="1", parent="1")
        ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y - 7), width=str(20), height=str(15), **{'as': 'geometry'})

    # --- NODE LAYOUT ---
    nodes["WEST"] = {"x": 50, "y": 50, "label": config["trunk"]["west_node"], "height": TRUNK_NODE_HEIGHT}
    current_col_x = 50 + NODE_WIDTH + LANE_WIDTH

    for bu in config["branches"]:
        nodes[bu["id"]] = {"x": current_col_x, "y": 50, "label": bu["label"], "height": TRUNK_NODE_HEIGHT}
        current_drop_y = 50 + TRUNK_NODE_HEIGHT + DROP_DEPTH

        # Pre-calculate X lanes for horizontal centering
        temp_fp_x = {}
        temp_shift = 0
        is_1x2 = bu.get("switch_type") == "1x2"

        for drop in bu["drops"]:
            for r in get_ranges(drop):
                is_new_bundle = False
                for i in range(r[0], r[1] + 1):
                    if i not in temp_fp_x:
                        if is_1x2:
                            temp_fp_x[i] = [current_col_x + temp_shift + 10, current_col_x + temp_shift + 16]
                            temp_shift += 12
                        else:
                            temp_fp_x[i] = [current_col_x + temp_shift + 10]
                            temp_shift += 6
                        is_new_bundle = True
                if is_new_bundle:
                    temp_shift += 15

        all_bu_x_vals = [x for lines in temp_fp_x.values() for x in lines]
        if all_bu_x_vals:
            bu_bundle_center = sum(all_bu_x_vals) / len(all_bu_x_vals)
            aligned_drop_x = bu_bundle_center - (NODE_WIDTH / 2)
        else:
            aligned_drop_x = current_col_x

        for drop in bu["drops"]:
            drop_height = 100
            if drop.get("sub_branches"):
                # Height driven by the total FP span across ALL bundles in this drop
                all_fps_in_drop = []
                for r in get_ranges(drop):
                    all_fps_in_drop.extend(range(r[0], r[1] + 1))
                if all_fps_in_drop:
                    fp_spread = max(all_fps_in_drop) - min(all_fps_in_drop)
                    drop_height = max(100, (fp_spread * FP_SPACING) + 60)

            nodes[drop["target_id"]] = {
                "x": aligned_drop_x, "y": current_drop_y,
                "label": drop["label"], "height": drop_height
            }

            for sub in drop.get("sub_branches", []):
                if sub.get("direction") == "east":
                    sub_x = aligned_drop_x + NODE_WIDTH + (LANE_WIDTH * 0.75)
                    nodes[sub["target_id"]] = {"x": sub_x, "y": current_drop_y, "label": sub["label"], "height": 100}
                else:
                    sub_y = current_drop_y + drop_height + DROP_DEPTH
                    nodes[sub["target_id"]] = {"x": aligned_drop_x, "y": sub_y, "label": sub["label"], "height": 100}

            current_drop_y += drop_height + DROP_DEPTH

        current_col_x += NODE_WIDTH + LANE_WIDTH

    nodes["EAST"] = {"x": current_col_x, "y": 50, "label": config["trunk"]["east_node"], "height": TRUNK_NODE_HEIGHT}

    for key, data in nodes.items():
        add_node(key, data["x"], data["y"], data["label"], data["height"])

    # --- TRUNK LINES ---
    for i in range(1, trunk_fps + 1):
        y_offset = nodes["WEST"]["y"] + (i * FP_SPACING) + 30
        add_line(f"fp_{i}_trunk", nodes["WEST"]["x"] + NODE_WIDTH, y_offset, nodes["EAST"]["x"], y_offset, fp_colors[i])
        add_label(i, nodes["WEST"]["x"] + NODE_WIDTH - 20, y_offset)
        add_label(i, nodes["EAST"]["x"] + 10, y_offset)

    # --- RENDER DROP ROUTING ---
    for bu in config["branches"]:
        fp_x_coords = {}
        current_bundle_shift_x = 0
        is_1x2 = bu.get("switch_type") == "1x2"

        for drop in bu["drops"]:
            for r in get_ranges(drop):
                start_fp, end_fp = r
                is_new_bundle = False
                for i in range(start_fp, end_fp + 1):
                    if i not in fp_x_coords:
                        if is_1x2:
                            x1 = nodes[bu["id"]]["x"] + current_bundle_shift_x + 10
                            x2 = x1 + 6
                            fp_x_coords[i] = [x1, x2]
                            current_bundle_shift_x += 12
                        else:
                            fp_x_coords[i] = [nodes[bu["id"]]["x"] + current_bundle_shift_x + 10]
                            current_bundle_shift_x += 6
                        is_new_bundle = True
                if is_new_bundle:
                    current_bundle_shift_x += 15

        fp_max_y = {}
        fp_sub_lines = []

        for drop in bu["drops"]:
            has_subs = bool(drop.get("sub_branches"))

            for r in get_ranges(drop):
                start_fp, end_fp = r
                for i in range(start_fp, end_fp + 1):
                    if not has_subs:
                        terminal_y = nodes[drop["target_id"]]["y"]
                        fp_max_y[i] = max(fp_max_y.get(i, 0), terminal_y)
                    else:
                        sub_bu_y = nodes[drop["target_id"]]["y"] + ((i - start_fp) * FP_SPACING) + 30
                        fp_max_y[i] = max(fp_max_y.get(i, 0), sub_bu_y)

                        for sub in drop["sub_branches"]:
                            # Iterate all sub-branch FP bundles via get_ranges() —
                            # handles both new fp_ranges and legacy fp_range transparently.
                            for sub_r in get_ranges(sub):
                                if sub_r[0] <= i <= sub_r[1]:
                                    if sub.get("direction") == "east":
                                        target_wall_x = nodes[sub["target_id"]]["x"]
                                        for x_coord in fp_x_coords.get(i, []):
                                            fp_sub_lines.append((
                                                f"fp_{i}_sub_east_{drop['target_id']}_{sub['target_id']}_{x_coord}",
                                                x_coord, sub_bu_y, target_wall_x, sub_bu_y, fp_colors[i]
                                            ))
                                    else:
                                        terminal_y = nodes[sub["target_id"]]["y"]
                                        fp_max_y[i] = max(fp_max_y.get(i, 0), terminal_y)

        for i, max_y in fp_max_y.items():
            trunk_y = nodes["WEST"]["y"] + (i * FP_SPACING) + 30
            for x_idx, x_coord in enumerate(fp_x_coords.get(i, [])):
                add_line(f"fp_{i}_{bu['id']}_main_bus_{x_idx}", x_coord, trunk_y, x_coord, max_y, fp_colors[i])
                add_dot(f"dot_{i}_{bu['id']}_{x_idx}", x_coord, trunk_y, fp_colors[i])

        for line_args in fp_sub_lines:
            add_line(*line_args)

    # --- SERIALIZE ---
    ET.indent(tree := ET.ElementTree(mxfile), space="\t", level=0)
    buffer = io.BytesIO()
    tree.write(buffer, encoding="utf-8", xml_declaration=True)
    return buffer.getvalue()


def generate_from_json(json_filepath, output_filepath):
    """Legacy file-based wrapper for CLI use."""
    with open(json_filepath, 'r') as f:
        config = json.load(f)
    xml_bytes = generate_from_config(config)
    with open(output_filepath, 'wb') as f:
        f.write(xml_bytes)


if __name__ == "__main__":
    generate_from_json("temp_payload.json", "output_topology.drawio")