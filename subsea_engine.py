import json
import xml.etree.ElementTree as ET
import io


def get_ranges(obj):
    if obj.get("fp_ranges"):
        return obj["fp_ranges"]
    if obj.get("fp_range"):
        return [obj["fp_range"]]
    return []


def generate_from_config(config):
    # --- VALIDATION GATE ---
    trunk_fps = config["trunk"]["total_fps"]
    seen_target_ids = set()
    fixed_consumed = {}

    for bu in config["branches"]:
        is_fixed = bu.get("routing_mode") == "fixed"
        for drop in bu["drops"]:
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
                    raise ValueError(f"BU '{bu['id']}' drop to '{tid}': FP range start ({start}) must be >= 1.")
                if start > end:
                    raise ValueError(f"BU '{bu['id']}' drop to '{tid}': FP range [{start}, {end}] is inverted.")
                if end > trunk_fps:
                    raise ValueError(f"BU '{bu['id']}' drop to '{tid}' references FP {end}, but trunk only has {trunk_fps} FPs.")
                for i in range(start, end + 1):
                    if i in fixed_consumed:
                        raise ValueError(
                            f"FP {i} in BU '{bu['id']}' drop to '{tid}' was already "
                            f"terminated at BU '{fixed_consumed[i]}' (fixed fibre routing)."
                        )
                    if is_fixed:
                        fixed_consumed[i] = bu["id"]
            for sub in drop.get("sub_branches", []):
                sub_tid = sub.get("target_id", "")
                if sub_tid in seen_target_ids:
                    raise ValueError(
                        f"Duplicate target_id '{sub_tid}' found in sub-branch under "
                        f"BU '{bu['id']}' / drop '{tid}'."
                    )
                seen_target_ids.add(sub_tid)
                for r in get_ranges(sub):
                    start, end = r
                    if start < 1:
                        raise ValueError(f"Sub-branch '{sub_tid}' under '{tid}': FP range start ({start}) must be >= 1.")
                    if start > end:
                        raise ValueError(f"Sub-branch '{sub_tid}' under '{tid}': FP range [{start}, {end}] is inverted.")
                    if end > trunk_fps:
                        raise ValueError(f"Sub-branch '{sub_tid}' under '{tid}' references FP {end}, but trunk only has {trunk_fps} FPs.")
        # Validate stubs
        for stub in bu.get("stubs", []):
            stid = stub.get("target_id", "")
            if not stid:
                raise ValueError(f"A stub in BU '{bu['id']}' is missing a target_id.")
            if stid in seen_target_ids:
                raise ValueError(f"Duplicate target_id '{stid}' in stub of BU '{bu['id']}'.")
            seen_target_ids.add(stid)
            stub_ranges = get_ranges(stub)
            if not stub_ranges:
                raise ValueError(f"Stub '{stid}' in BU '{bu['id']}' has no FP ranges defined.")
            for r in stub_ranges:
                start, end = r
                if start < 1:
                    raise ValueError(f"Stub '{stid}': FP range start ({start}) must be >= 1.")
                if start > end:
                    raise ValueError(f"Stub '{stid}': FP range [{start}, {end}] is inverted.")
                if end > trunk_fps:
                    raise ValueError(f"Stub '{stid}' references FP {end}, but trunk only has {trunk_fps} FPs.")

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

    # --- SPACING & LAYOUT CONSTANTS ---
    # All four spacing values are user-configurable via the UI.
    FP_SPACING        = max(10, min(60,  int(config["trunk"].get("fp_spacing",  20))))
    LANE_WIDTH        = max(50, min(400, int(config["trunk"].get("lane_width", 250))))
    DROP_DEPTH        = max(50, min(400, int(config["trunk"].get("drop_depth", 150))))
    # LINE_GAP: gap between individual FP vertical lines within a BU (default 6 px).
    # BUNDLE_GAP: extra gap inserted between non-contiguous FP bundles = LINE_GAP * 2.5.
    LINE_GAP          = max(2,  min(30,  int(config["trunk"].get("line_gap",    6))))
    BUNDLE_GAP        = max(1, round(LINE_GAP * 2.5))
    NODE_WIDTH        = 250
    TRUNK_NODE_HEIGHT = max(420, (trunk_fps * FP_SPACING) + 60)
    nodes             = {}

    # --- COLOR MAPPING ---
    fp_colors = {i: "#0050ef" for i in range(1, trunk_fps + 1)}
    for rule in config["trunk"].get("colors", []):
        start_fp, end_fp = rule["fp_range"]
        for i in range(max(1, start_fp), min(trunk_fps, end_fp) + 1):
            fp_colors[i] = rule["color"]

    # --- PRIMITIVE HELPERS ---
    def add_node(node_id, x, y, label, height=TRUNK_NODE_HEIGHT, node_type="trunk", inactive=False):
        if node_type == "stub":
            style = (
                "rounded=1;whiteSpace=wrap;html=1;"
                "fillColor=#fff2cc;strokeColor=#d79b00;strokeWidth=2;"
                "verticalAlign=top;align=left;spacingLeft=8;spacingTop=6;"
            )
            cell = ET.SubElement(root, 'mxCell', id=node_id, value=label, style=style, vertex="1", parent="1")
            ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y),
                          width=str(NODE_WIDTH), height=str(height), **{'as': 'geometry'})
            return
        if node_type in ("drop", "sub"):
            if inactive:
                style = (
                    "rounded=1;whiteSpace=wrap;html=1;"
                    "fillColor=#f0f0f0;strokeColor=#aaaaaa;"
                    "dashed=1;dashPattern=8 4;"
                    "verticalAlign=top;align=left;spacingLeft=8;spacingTop=6;"
                    "opacity=70;fontColor=#999999;"
                )
            else:
                style = (
                    "rounded=1;whiteSpace=wrap;html=1;"
                    "fillColor=#f5f5f5;strokeColor=#666666;"
                    "verticalAlign=top;align=left;spacingLeft=8;spacingTop=6;"
                )
        else:
            style = (
                "rounded=1;whiteSpace=wrap;html=1;"
                "fillColor=#f5f5f5;strokeColor=#666666;"
                "verticalAlign=top;align=center;spacingTop=8;"
            )
        cell = ET.SubElement(root, 'mxCell', id=node_id, value=label, style=style, vertex="1", parent="1")
        ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y),
                      width=str(NODE_WIDTH), height=str(height), **{'as': 'geometry'})

    def add_line(line_id, start_x, start_y, end_x, end_y, color):
        style = f"endArrow=none;html=1;rounded=0;strokeColor={color};"
        cell = ET.SubElement(root, 'mxCell', id=line_id, style=style, edge="1", parent="1")
        geometry = ET.SubElement(cell, 'mxGeometry', relative="1", **{'as': 'geometry'})
        ET.SubElement(geometry, 'mxPoint', x=str(start_x), y=str(start_y), **{'as': 'sourcePoint'})
        ET.SubElement(geometry, 'mxPoint', x=str(end_x),   y=str(end_y),   **{'as': 'targetPoint'})

    def add_dot(dot_id, x, y, color):
        style = f"ellipse;whiteSpace=wrap;html=1;aspect=fixed;fillColor={color};strokeColor=none;perimeter=none;"
        cell = ET.SubElement(root, 'mxCell', id=dot_id, value="", style=style, vertex="1", parent="1")
        ET.SubElement(cell, 'mxGeometry', x=str(x - 3), y=str(y - 3),
                      width="6", height="6", **{'as': 'geometry'})

    def place_intersection_marker(marker_id, x, y, color, switch_pos):
        """
        default → small filled dot (6 px) in the FP colour — existing behaviour.
        pos1    → 14 px red circle with "1" (switch open: trunk through).
        pos2    → 14 px red circle with "2" (switch closed: trunk to branch).
        Red (#e51400 / #B20000) matches the user-supplied legend illustration.
        """
        if switch_pos == "default":
            add_dot(marker_id, x, y, color)
            return
        CIRCLE_SIZE = 14
        num   = "1" if switch_pos == "pos1" else "2"
        style = (
            "ellipse;whiteSpace=wrap;html=1;aspect=fixed;"
            "fillColor=#e51400;strokeColor=#B20000;strokeWidth=1;"
            "fontColor=#ffffff;fontSize=8;fontStyle=1;"
            "align=center;verticalAlign=middle;"
        )
        cell = ET.SubElement(root, 'mxCell', id=marker_id, value=num,
                             style=style, vertex="1", parent="1")
        ET.SubElement(cell, 'mxGeometry',
                      x=str(int(x) - CIRCLE_SIZE // 2),
                      y=str(int(y) - CIRCLE_SIZE // 2),
                      width=str(CIRCLE_SIZE), height=str(CIRCLE_SIZE),
                      **{'as': 'geometry'})

    def add_label(text, x, y):
        style = "text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontSize=9;"
        cell = ET.SubElement(root, 'mxCell', value=str(text), style=style, vertex="1", parent="1")
        ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y - 7),
                      width="20", height="15", **{'as': 'geometry'})

    def split_hairpin_coords(coords):
        """Split a hairpin FP coord list into (down_coords, up_coords).

        For 1x1 hairpin coords = [x_down, x_up]   → down=[x_down], up=[x_up]
        For 1x2 hairpin coords = [d1, d2, u1, u2]  → down=[d1, d2], up=[u1, u2]
        The first half of the list are the 'down' (West-side) lines; the second
        half are the 'up' (East-side) lines that complete the U-turn.
        """
        mid = len(coords) // 2
        return coords[:mid], coords[mid:]

    # --- NODE LAYOUT ---
    nodes["WEST"] = {
        "x": 50, "y": 50, "label": config["trunk"]["west_node"],
        "height": TRUNK_NODE_HEIGHT, "node_type": "trunk"
    }
    current_col_x = 50 + NODE_WIDTH + LANE_WIDTH

    for bu in config["branches"]:
        switch_pos   = bu.get("switch_position", "default")
        routing_mode = bu.get("routing_mode", "express")
        # Hairpin drop nodes are always rendered active (not ghosted).
        bu_inactive  = (switch_pos == "pos1") and (routing_mode != "hairpin")

        nodes[bu["id"]] = {
            "x": current_col_x, "y": 50, "label": bu["label"],
            "height": TRUNK_NODE_HEIGHT, "node_type": "trunk"
        }
        current_drop_y = 50 + TRUNK_NODE_HEIGHT + DROP_DEPTH

        temp_fp_x   = {}
        temp_shift  = 0
        is_1x2      = bu.get("switch_type") == "1x2"
        is_hairpin  = (routing_mode == "hairpin")

        for item in list(bu["drops"]) + bu.get("stubs", []):
            for r in get_ranges(item):
                is_new_bundle = False
                for i in range(r[0], r[1] + 1):
                    if i not in temp_fp_x:
                        base_x = current_col_x + temp_shift + 10
                        if is_hairpin:
                            if is_1x2:
                                # 4 coords: [x_d1, x_d2, x_u1, x_u2]
                                temp_fp_x[i] = [base_x,
                                                base_x + LINE_GAP,
                                                base_x + LINE_GAP * 2,
                                                base_x + LINE_GAP * 3]
                                temp_shift += LINE_GAP * 4
                            else:
                                # 2 coords: [x_down, x_up]
                                temp_fp_x[i] = [base_x, base_x + LINE_GAP]
                                temp_shift += LINE_GAP * 2
                        elif is_1x2:
                            temp_fp_x[i] = [base_x, base_x + LINE_GAP]
                            temp_shift += LINE_GAP * 2
                        else:
                            temp_fp_x[i] = [base_x]
                            temp_shift += LINE_GAP
                        is_new_bundle = True
                if is_new_bundle:
                    temp_shift += BUNDLE_GAP

        all_bu_x = [x for lines in temp_fp_x.values() for x in lines]
        aligned_drop_x = (sum(all_bu_x) / len(all_bu_x) - NODE_WIDTH / 2) if all_bu_x else current_col_x

        for drop in bu["drops"]:
            drop_height = 100
            if drop.get("sub_branches"):
                all_fps = []
                for r in get_ranges(drop):
                    all_fps.extend(range(r[0], r[1] + 1))
                if all_fps:
                    drop_height = max(100, ((max(all_fps) - min(all_fps)) * FP_SPACING) + 60)

            nodes[drop["target_id"]] = {
                "x": aligned_drop_x, "y": current_drop_y,
                "label": drop["label"], "height": drop_height,
                "node_type": "drop", "inactive": bu_inactive,
            }

            for sub in drop.get("sub_branches", []):
                sub_all_fps = []
                for sr in get_ranges(sub):
                    sub_all_fps.extend(range(sr[0], sr[1] + 1))
                sub_height = max(100, ((max(sub_all_fps) - min(sub_all_fps)) * FP_SPACING) + 60) if sub_all_fps else 100

                if sub.get("direction") == "east":
                    nodes[sub["target_id"]] = {
                        "x": aligned_drop_x + NODE_WIDTH + LANE_WIDTH * 0.75,
                        "y": current_drop_y,
                        "label": sub["label"], "height": sub_height,
                        "node_type": "sub", "inactive": bu_inactive,
                    }
                else:
                    nodes[sub["target_id"]] = {
                        "x": aligned_drop_x,
                        "y": current_drop_y + drop_height + DROP_DEPTH,
                        "label": sub["label"], "height": sub_height,
                        "node_type": "sub", "inactive": bu_inactive,
                    }

            current_drop_y += drop_height + DROP_DEPTH

        # Place stub nodes (amber, same height as a plain drop)
        for stub in bu.get("stubs", []):
            stub_height = 100
            nodes[stub["target_id"]] = {
                "x": aligned_drop_x, "y": current_drop_y,
                "label": stub.get("label", "Stub"),
                "height": stub_height,
                "node_type": "stub",
            }
            current_drop_y += stub_height + DROP_DEPTH

        current_col_x += NODE_WIDTH + LANE_WIDTH

    nodes["EAST"] = {
        "x": current_col_x, "y": 50, "label": config["trunk"]["east_node"],
        "height": TRUNK_NODE_HEIGHT, "node_type": "trunk"
    }

    for key, data in nodes.items():
        add_node(key, data["x"], data["y"], data["label"],
                 data["height"], data.get("node_type", "trunk"),
                 data.get("inactive", False))

    # --- TRUNK LINES ---
    # trunk_segs[i] = list of (start_x, end_x) horizontal segments for FP i.
    # Most FPs have a single segment (WEST→EAST). Fixed routing truncates it.
    # Hairpin routing splits it into two: WEST→x_down and x_up→EAST (or next).
    WEST_right_x = nodes["WEST"]["x"] + NODE_WIDTH
    EAST_x       = nodes["EAST"]["x"]
    trunk_segs   = {i: [(WEST_right_x, EAST_x)] for i in range(1, trunk_fps + 1)}

    for bu in config["branches"]:
        _rm = bu.get("routing_mode", "express")
        if _rm == "fixed":
            bu_right_x = nodes[bu["id"]]["x"] + NODE_WIDTH
            for drop in bu["drops"]:
                for r in get_ranges(drop):
                    for i in range(r[0], r[1] + 1):
                        if trunk_segs[i][-1][1] >= EAST_x:
                            trunk_segs[i][-1] = (trunk_segs[i][-1][0], bu_right_x)
        elif _rm == "hairpin":
            # Re-compute fp_x_coords for this BU to find x_down / x_up per FP.
            _is_1x2 = bu.get("switch_type") == "1x2"
            _fp_x   = {}
            _shift  = 0
            for item in list(bu["drops"]) + bu.get("stubs", []):
                for r in get_ranges(item):
                    _new_bundle = False
                    for i in range(r[0], r[1] + 1):
                        if i not in _fp_x:
                            bx = nodes[bu["id"]]["x"] + _shift + 10
                            if _is_1x2:
                                _fp_x[i] = [bx, bx+LINE_GAP, bx+LINE_GAP*2, bx+LINE_GAP*3]
                                _shift += LINE_GAP * 4
                            else:
                                _fp_x[i] = [bx, bx + LINE_GAP]
                                _shift += LINE_GAP * 2
                            _new_bundle = True
                    if _new_bundle:
                        _shift += BUNDLE_GAP
            for i, coords in _fp_x.items():
                down_c, up_c = split_hairpin_coords(coords)
                x_down = down_c[0]       # West trunk ends at the first down line
                x_up   = up_c[0]         # East trunk starts at the first up line
                segs   = trunk_segs[i]
                last_start, last_end = segs[-1]
                segs[-1] = (last_start, x_down)      # Truncate existing segment
                segs.append((x_up, last_end))         # New segment from x_up onward

    for i in range(1, trunk_fps + 1):
        y_off = nodes["WEST"]["y"] + (i * FP_SPACING) + 30
        for seg_idx, (sx, ex) in enumerate(trunk_segs[i]):
            lid = f"fp_{i}_trunk" if seg_idx == 0 else f"fp_{i}_trunk_{seg_idx}"
            add_line(lid, sx, y_off, ex, y_off, fp_colors[i])
        add_label(i, WEST_right_x - 20, y_off)
        if trunk_segs[i][-1][1] >= EAST_x:
            add_label(i, EAST_x + 10, y_off)

    # --- CABLE SEGMENT LABELS ---
    # Optional per-segment name labels drawn above the trunk span.
    # Config: config["trunk"]["segments"] = [{"label": "Seg A–B", "length": "120 km"}, ...]
    # One entry per gap: index 0 = WEST→BU1, 1 = BU1→BU2, …, last = BUn→EAST.
    seg_labels = config["trunk"].get("segments", [])
    if seg_labels:
        # Build ordered list of trunk-node x positions (left wall of each node)
        trunk_node_xs = [nodes["WEST"]["x"] + NODE_WIDTH]
        for bu in config["branches"]:
            trunk_node_xs.append(nodes[bu["id"]]["x"])
            trunk_node_xs.append(nodes[bu["id"]]["x"] + NODE_WIDTH)
        trunk_node_xs.append(nodes["EAST"]["x"])
        # Pair them into spans: (right_wall_of_left_node, left_wall_of_right_node)
        spans = [(trunk_node_xs[i], trunk_node_xs[i+1])
                 for i in range(0, len(trunk_node_xs)-1, 2)]
        label_y = nodes["WEST"]["y"] + 18   # above top FP line
        for idx, seg in enumerate(seg_labels):
            if idx >= len(spans):
                break
            x1, x2    = spans[idx]
            mid_x     = (x1 + x2) / 2
            seg_text  = seg.get("label", "")
            seg_len   = seg.get("length", "")
            display   = f"{seg_text}<br/><font style='font-size:8px;color:#888'>{seg_len}</font>" if seg_len else seg_text
            lbl_style = ("text;html=1;strokeColor=none;fillColor=none;"
                         "align=center;verticalAlign=bottom;whiteSpace=wrap;"
                         "rounded=0;fontSize=10;fontStyle=1;")
            lbl_w = max(80, x2 - x1 - 10)
            cell = ET.SubElement(root, 'mxCell', id=f"seg_label_{idx}",
                                 value=display, style=lbl_style, vertex="1", parent="1")
            ET.SubElement(cell, 'mxGeometry',
                          x=str(mid_x - lbl_w / 2), y=str(label_y - 30),
                          width=str(lbl_w), height="28", **{'as': 'geometry'})

    # --- RENDER DROP ROUTING ---
    for bu in config["branches"]:
        switch_pos   = bu.get("switch_position", "default")
        routing_mode = bu.get("routing_mode", "express")

        fp_x_coords = {}
        cur_shift   = 0
        is_1x2      = bu.get("switch_type") == "1x2"
        is_hairpin  = (routing_mode == "hairpin")

        for item in list(bu["drops"]) + bu.get("stubs", []):
            for r in get_ranges(item):
                is_new_bundle = False
                for i in range(r[0], r[1] + 1):
                    if i not in fp_x_coords:
                        base_x = nodes[bu["id"]]["x"] + cur_shift + 10
                        if is_hairpin:
                            if is_1x2:
                                fp_x_coords[i] = [base_x,
                                                  base_x + LINE_GAP,
                                                  base_x + LINE_GAP * 2,
                                                  base_x + LINE_GAP * 3]
                                cur_shift += LINE_GAP * 4
                            else:
                                fp_x_coords[i] = [base_x, base_x + LINE_GAP]
                                cur_shift += LINE_GAP * 2
                        elif is_1x2:
                            fp_x_coords[i] = [base_x, base_x + LINE_GAP]
                            cur_shift += LINE_GAP * 2
                        else:
                            fp_x_coords[i] = [base_x]
                            cur_shift += LINE_GAP
                        is_new_bundle = True
                if is_new_bundle:
                    cur_shift += BUNDLE_GAP

        if is_hairpin:
            # Collect all FPs that belong to this hairpin BU.
            all_hp_fps = set()
            for drop in bu["drops"]:
                for r in get_ranges(drop):
                    all_hp_fps.update(range(r[0], r[1] + 1))

            # Shared terminal Y = deepest (maximum Y) drop node among all drops.
            terminal_y = 0
            for drop in bu["drops"]:
                terminal_y = max(terminal_y, nodes[drop["target_id"]]["y"])

            # Draw the hairpin vertical lines for each FP — no markers.
            for i in sorted(all_hp_fps):
                coords = fp_x_coords.get(i, [])
                if not coords:
                    continue
                trunk_y              = nodes["WEST"]["y"] + (i * FP_SPACING) + 30
                down_coords, up_coords = split_hairpin_coords(coords)

                for idx, x_d in enumerate(down_coords):
                    add_line(f"fp_{i}_{bu['id']}_hp_down_{idx}",
                             x_d, trunk_y, x_d, terminal_y, fp_colors[i])
                for idx, x_u in enumerate(up_coords):
                    add_line(f"fp_{i}_{bu['id']}_hp_up_{idx}",
                             x_u, terminal_y, x_u, trunk_y, fp_colors[i])
                # Horizontal bar at terminal_y connecting last down → first up
                if down_coords and up_coords:
                    add_line(f"fp_{i}_{bu['id']}_hp_bar",
                             down_coords[-1], terminal_y,
                             up_coords[0],   terminal_y, fp_colors[i])

        elif switch_pos == "pos1":
            # Trunk passes straight through — numbered markers only, no branch lines.
            bu_fps = set()
            for drop in bu["drops"]:
                for r in get_ranges(drop):
                    bu_fps.update(range(r[0], r[1] + 1))
            for i in sorted(bu_fps):
                trunk_y = nodes["WEST"]["y"] + (i * FP_SPACING) + 30
                for x_idx, x_coord in enumerate(fp_x_coords.get(i, [])):
                    place_intersection_marker(
                        f"switch_{i}_{bu['id']}_{x_idx}",
                        x_coord, trunk_y, fp_colors[i], "pos1"
                    )
        else:
            # Default / pos2 — draw vertical branch lines with appropriate markers.
            fp_max_y     = {}
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
                            sub_bu_y = (nodes[drop["target_id"]]["y"]
                                        + ((i - start_fp) * FP_SPACING) + 30)
                            fp_max_y[i] = max(fp_max_y.get(i, 0), sub_bu_y)
                            for sub in drop["sub_branches"]:
                                for sub_r in get_ranges(sub):
                                    if sub_r[0] <= i <= sub_r[1]:
                                        if sub.get("direction") == "east":
                                            target_wall_x = nodes[sub["target_id"]]["x"]
                                            for x_idx, x_coord in enumerate(fp_x_coords.get(i, [])):
                                                east_y = sub_bu_y + x_idx * 3
                                                fp_sub_lines.append((
                                                    f"fp_{i}_sub_east_{drop['target_id']}_{sub['target_id']}_{x_idx}",
                                                    x_coord, east_y, target_wall_x, east_y, fp_colors[i]
                                                ))
                                        else:
                                            terminal_y = nodes[sub["target_id"]]["y"]
                                            fp_max_y[i] = max(fp_max_y.get(i, 0), terminal_y)

            for i, max_y in fp_max_y.items():
                trunk_y = nodes["WEST"]["y"] + (i * FP_SPACING) + 30
                for x_idx, x_coord in enumerate(fp_x_coords.get(i, [])):
                    add_line(f"fp_{i}_{bu['id']}_main_bus_{x_idx}",
                             x_coord, trunk_y, x_coord, max_y, fp_colors[i])
                    place_intersection_marker(
                        f"switch_{i}_{bu['id']}_{x_idx}",
                        x_coord, trunk_y, fp_colors[i], switch_pos
                    )

            for drop in bu["drops"]:
                if not drop.get("sub_branches"):
                    continue
                for r in get_ranges(drop):
                    start_fp, end_fp = r
                    for i in range(start_fp, end_fp + 1):
                        jy = (nodes[drop["target_id"]]["y"]
                              + ((i - start_fp) * FP_SPACING) + 30)
                        for x_idx, x_coord in enumerate(fp_x_coords.get(i, [])):
                            add_dot(f"dot_drop_entry_{i}_{drop['target_id']}_{x_idx}",
                                    x_coord, jy, fp_colors[i])

            for line_args in fp_sub_lines:
                add_line(*line_args)

        # ── STUB RENDERING ────────────────────────────────────────────────────
        # Each stub renders independently with its own switch_position.
        # 1x1: vertical lines drop into the stub and terminate (no exit).
        # 1x2: same, plus a horizontal joining bar connects paired lines
        #      at the terminal point — showing the fibres are joined inside.
        for stub in bu.get("stubs", []):
            stub_switch_pos = stub.get("switch_position", "default")
            stub_node       = nodes[stub["target_id"]]
            stub_bot_y      = stub_node["y"] + stub_node["height"] - 18

            # Collect all FPs in this stub across all its bundles
            stub_fps = []
            for r in get_ranges(stub):
                stub_fps.extend(range(r[0], r[1] + 1))

            if stub_switch_pos == "pos1":
                # Trunk passes through — markers only, no vertical lines
                for i in stub_fps:
                    trunk_y = nodes["WEST"]["y"] + (i * FP_SPACING) + 30
                    for x_idx, x_coord in enumerate(fp_x_coords.get(i, [])):
                        place_intersection_marker(
                            f"switch_stub_{i}_{stub['target_id']}_{x_idx}",
                            x_coord, trunk_y, fp_colors[i], "pos1"
                        )
            else:
                # Draw vertical lines from trunk down into stub
                for i in stub_fps:
                    trunk_y = nodes["WEST"]["y"] + (i * FP_SPACING) + 30
                    for x_idx, x_coord in enumerate(fp_x_coords.get(i, [])):
                        add_line(
                            f"fp_{i}_{stub['target_id']}_stub_{x_idx}",
                            x_coord, trunk_y, x_coord, stub_bot_y, fp_colors[i]
                        )
                        place_intersection_marker(
                            f"switch_stub_{i}_{stub['target_id']}_{x_idx}",
                            x_coord, trunk_y, fp_colors[i], stub_switch_pos
                        )

                # For 1x2: draw horizontal joining bars at stub_bot_y,
                # one bar per contiguous pair of x-coords (x1, x2) per FP.
                if is_1x2:
                    drawn_bars = set()
                    for i in stub_fps:
                        coords = fp_x_coords.get(i, [])
                        if len(coords) == 2:
                            x1, x2 = coords[0], coords[1]
                            bar_key = (round(x1, 1), round(x2, 1))
                            if bar_key not in drawn_bars:
                                add_line(
                                    f"stub_bar_{stub['target_id']}_{i}",
                                    x1, stub_bot_y, x2, stub_bot_y, fp_colors[i]
                                )
                                drawn_bars.add(bar_key)
                else:
                    # 1x1: draw a short horizontal termination cap at stub_bot_y
                    CAP_W = 6
                    for i in stub_fps:
                        for x_idx, x_coord in enumerate(fp_x_coords.get(i, [])):
                            cap_key = f"stub_cap_{stub['target_id']}_{i}_{x_idx}"
                            add_line(
                                cap_key,
                                x_coord - CAP_W // 2, stub_bot_y,
                                x_coord + CAP_W // 2, stub_bot_y,
                                fp_colors[i]
                            )

    # --- LEGENDS ---
    def add_color_legend(lx, ly):
        colors_config = config["trunk"].get("colors", [])
        if not colors_config:
            return 0
        DEFAULT_COLOR = "#0050ef"
        LEGEND_WIDTH  = 230
        ROW_HEIGHT    = 28
        H_PAD         = 12
        SWATCH_W      = 30
        TITLE_H       = 30

        color_to_ranges = {}
        covered_fps = set()
        for rule in colors_config:
            s = max(1, rule["fp_range"][0])
            e = min(trunk_fps, rule["fp_range"][1])
            c = rule["color"]
            color_to_ranges.setdefault(c, []).append((s, e))
            covered_fps.update(range(s, e + 1))

        default_fps = sorted(i for i in range(1, trunk_fps + 1) if i not in covered_fps)

        def to_ranges(fps):
            if not fps:
                return []
            ranges, start, prev = [], fps[0], fps[0]
            for fp in fps[1:]:
                if fp == prev + 1:
                    prev = fp
                else:
                    ranges.append((start, prev))
                    start = prev = fp
            ranges.append((start, prev))
            return ranges

        def ranges_label(pairs):
            return "FPs: " + ", ".join(f"{s}–{e}" if s != e else str(s) for s, e in sorted(pairs))

        entries = []
        if default_fps:
            entries.append((ranges_label(to_ranges(default_fps)), DEFAULT_COLOR))
        for color, pairs in color_to_ranges.items():
            entries.append((ranges_label(pairs), color))

        legend_height = TITLE_H + len(entries) * ROW_HEIGHT + H_PAD
        box_style = (
            "rounded=1;whiteSpace=wrap;html=1;"
            "fillColor=#ffffff;strokeColor=#666666;"
            "verticalAlign=top;align=left;"
            "spacingTop=6;spacingLeft=10;fontSize=11;fontStyle=1;"
        )
        box = ET.SubElement(root, 'mxCell', id="legend_box", value="Legend",
                            style=box_style, vertex="1", parent="1")
        ET.SubElement(box, 'mxGeometry', x=str(lx), y=str(ly),
                      width=str(LEGEND_WIDTH), height=str(legend_height),
                      **{'as': 'geometry'})
        for idx, (label, color) in enumerate(entries):
            row_y    = ly + TITLE_H + idx * ROW_HEIGHT
            swatch_y = row_y + ROW_HEIGHT // 2
            sw_style = f"endArrow=none;html=1;rounded=0;strokeColor={color};strokeWidth=3;"
            sw_cell  = ET.SubElement(root, 'mxCell', id=f"legend_swatch_{idx}",
                                     style=sw_style, edge="1", parent="1")
            sw_geom  = ET.SubElement(sw_cell, 'mxGeometry', relative="1", **{'as': 'geometry'})
            ET.SubElement(sw_geom, 'mxPoint', x=str(lx + H_PAD),            y=str(swatch_y), **{'as': 'sourcePoint'})
            ET.SubElement(sw_geom, 'mxPoint', x=str(lx + H_PAD + SWATCH_W), y=str(swatch_y), **{'as': 'targetPoint'})
            txt_style = (
                "text;html=1;strokeColor=none;fillColor=none;"
                "align=left;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontSize=10;"
            )
            t_cell = ET.SubElement(root, 'mxCell', id=f"legend_label_{idx}", value=label,
                                   style=txt_style, vertex="1", parent="1")
            ET.SubElement(t_cell, 'mxGeometry',
                          x=str(lx + H_PAD + SWATCH_W + 8), y=str(row_y),
                          width=str(LEGEND_WIDTH - H_PAD - SWATCH_W - 20),
                          height=str(ROW_HEIGHT), **{'as': 'geometry'})
        return LEGEND_WIDTH

    def add_switch_legend(lx, ly):
        """
        Reproduces the user-supplied switch-position legend verbatim,
        offset so its top-left corner lands at (lx, ly).
        Reference origin in the uploaded XML: box at (170, 290).
        """
        REF_X, REF_Y = 170, 290
        dx = lx - REF_X
        dy = ly - REF_Y

        def fx(x): return str(round(x + dx, 2))
        def fy(y): return str(round(y + dy, 2))

        def v_edge(eid, x1, y1, x2, y2, style):
            cell = ET.SubElement(root, 'mxCell', id=eid, style=style, edge="1", parent="1")
            g = ET.SubElement(cell, 'mxGeometry', relative="1", **{'as': 'geometry'})
            ET.SubElement(g, 'mxPoint', x=fx(x1), y=fy(y1), **{'as': 'sourcePoint'})
            ET.SubElement(g, 'mxPoint', x=fx(x2), y=fy(y2), **{'as': 'targetPoint'})

        def v_ellipse(eid, x, y, w, h, style, value=""):
            cell = ET.SubElement(root, 'mxCell', id=eid, value=value, style=style,
                                 vertex="1", parent="1")
            ET.SubElement(cell, 'mxGeometry', x=fx(x), y=fy(y),
                          width=str(w), height=str(h), **{'as': 'geometry'})

        def v_text(tid, value, x, y, w, h):
            style = ("text;html=1;strokeColor=none;fillColor=none;align=left;"
                     "verticalAlign=middle;whiteSpace=wrap;rounded=0;fontSize=10;")
            cell = ET.SubElement(root, 'mxCell', id=tid, value=value, style=style,
                                 vertex="1", parent="1")
            ET.SubElement(cell, 'mxGeometry', x=fx(x), y=fy(y),
                          width=str(w), height=str(h), **{'as': 'geometry'})

        # Style constants — match the uploaded XML exactly
        GREY  = "endArrow=none;html=1;rounded=0;strokeColor=#555555;strokeWidth=2;"
        RED_E = "endArrow=none;html=1;rounded=0;strokeColor=#B20000;strokeWidth=2;fillColor=#e51400;"
        DOT_B = "ellipse;whiteSpace=wrap;html=1;aspect=fixed;fillColor=#0050ef;strokeColor=none;"
        DOT_R = "ellipse;whiteSpace=wrap;html=1;aspect=fixed;fillColor=#e51400;strokeColor=#B20000;fontSize=3;fontColor=#ffffff;"
        CIR_R = ("ellipse;whiteSpace=wrap;html=1;aspect=fixed;"
                 "fillColor=#e51400;strokeColor=#B20000;strokeWidth=1;"
                 "fontColor=#ffffff;fontSize=8;fontStyle=1;"
                 "align=center;verticalAlign=middle;")

        # Outer box
        sw_box = ET.SubElement(root, 'mxCell', id="sw_legend_box",
            value="Switch Positions",
            style="rounded=1;whiteSpace=wrap;html=1;fillColor=#ffffff;"
                  "strokeColor=#666666;verticalAlign=top;align=left;"
                  "spacingTop=6;spacingLeft=10;fontSize=11;fontStyle=1;",
            vertex="1", parent="1")
        ET.SubElement(sw_box, 'mxGeometry', x=fx(170), y=fy(290),
                      width="260", height="250", **{'as': 'geometry'})

        # ── Row 1: Default ──────────────────────────────────────────────────────
        v_edge    ("sw_r1_h",   182, 338, 232, 338,  GREY)
        v_ellipse ("sw_r1_dot", 202, 333, 10,  10,   DOT_B)
        v_text    ("sw_r1_lbl", "Default — dot",          240, 320, 178, 36)

        # ── Row 2: Pos 1 — Trunk Through ────────────────────────────────────────
        v_edge    ("sw_r2_h",   182, 374, 232, 374,  GREY)
        v_ellipse ("sw_r2_c",   200, 367, 14,  14,   CIR_R, "1")
        v_text    ("sw_r2_lbl", "Pos. 1 — Trunk Through", 240, 356, 178, 36)
        v_edge    ("sw_r2_i01", 254,    392,    290,    392,    GREY)
        v_ellipse ("sw_r2_i02", 289,    389,    6,      6,      DOT_R)
        v_edge    ("sw_r2_i03", 295,    391.86, 312,    391.86, RED_E)
        v_ellipse ("sw_r2_i04", 306,    389,    6,      6,      DOT_R)
        v_edge    ("sw_r2_i05", 312,    392,    329,    392,    GREY)
        v_ellipse ("sw_r2_i06", 329,    389,    6,      6,      DOT_R)
        v_edge    ("sw_r2_i07", 335,    391.86, 352,    391.86, RED_E)
        v_ellipse ("sw_r2_i08", 346,    389,    6,      6,      DOT_R)
        v_edge    ("sw_r2_i09", 352,    392,    388,    392,    GREY)
        v_edge    ("sw_r2_i10", 291.86, 400,    291.86, 436,    GREY)
        v_edge    ("sw_r2_i11", 348.86, 400,    348.86, 436,    GREY)

        # ── Row 3: Pos 2 — Trunk to Branch ──────────────────────────────────────
        v_edge    ("sw_r3_h",   182,    457,    232,    457,    GREY)
        v_edge    ("sw_r3_vs",  207,    457,    207,    469,    GREY)
        v_ellipse ("sw_r3_c",   200,    450,    14,     14,     CIR_R, "2")
        v_text    ("sw_r3_lbl", "Pos. 2 — Trunk to Branch", 240, 439, 178, 36)
        v_edge    ("sw_r3_i01", 256,    478,    292,    478,    GREY)
        v_ellipse ("sw_r3_i02", 291,    475,    6,      6,      DOT_R)
        v_edge    ("sw_r3_i03", 293.86, 481,    293.86, 517,    RED_E)
        v_edge    ("sw_r3_i04", 314,    478,    331,    478,    GREY)
        v_ellipse ("sw_r3_i05", 331,    475,    6,      6,      DOT_R)
        v_ellipse ("sw_r3_i06", 348,    475,    6,      6,      DOT_R)
        v_edge    ("sw_r3_i07", 354,    478,    390,    478,    GREY)
        v_edge    ("sw_r3_i08", 293.86, 500,    293.86, 536,    GREY)
        v_edge    ("sw_r3_i09", 350.86, 481,    350.86, 517,    RED_E)
        v_edge    ("sw_r3_i10", 350.86, 500,    350.86, 536,    GREY)
        v_ellipse ("sw_r3_i11", 291,    500,    6,      6,      DOT_R)
        v_ellipse ("sw_r3_i12", 348,    500,    6,      6,      DOT_R)
        v_ellipse ("sw_r3_i13", 312,    475,    6,      6,      DOT_R)

    def add_legends():
        # Both legends left-aligned under the WEST node, stacked vertically.
        # Color legend is optional; switch legend always appears.
        COLOR_LEGEND_HEIGHT = 30  # title
        COLOR_ROW_H         = 28
        H_PAD               = 12

        lx = int(nodes["WEST"]["x"])
        ly = int(nodes["WEST"]["y"] + TRUNK_NODE_HEIGHT + 60)

        # Measure how tall the color legend will be (0 if no color rules)
        colors_config = config["trunk"].get("colors", [])
        if colors_config:
            # count distinct entries: default band (if any) + one per color rule
            covered = set()
            for rule in colors_config:
                covered.update(range(max(1, rule["fp_range"][0]),
                                     min(trunk_fps, rule["fp_range"][1]) + 1))
            default_count = 1 if any(i not in covered for i in range(1, trunk_fps + 1)) else 0
            n_entries = default_count + len(set(r["color"] for r in colors_config))
            color_box_h = COLOR_LEGEND_HEIGHT + n_entries * COLOR_ROW_H + H_PAD
        else:
            color_box_h = 0

        add_color_legend(lx, ly)
        gap = 20 if color_box_h else 0
        add_switch_legend(lx, ly + color_box_h + gap)

    add_legends()

    # --- FIBRE COUNT SUMMARY TABLE ---
    def add_fibre_summary(lx, ly):
        """
        Table below the legends.
        Rows: one per BU showing dropped/stub FPs and pass-through count.
        Columns: Segment | Dropped FPs | Pass-through FPs | Notes
        """
        tb_meta = config.get("title_block", {})
        if not tb_meta.get("show_fibre_summary", True):
            return 0

        COL_W   = [120, 110, 130, 140]   # Segment, Dropped, Pass-through, Notes
        ROW_H   = 24
        TITLE_H = 28
        PAD     = 8

        total_w = sum(COL_W)
        headers = ["Segment", "Dropped FPs", "Pass-through FPs", "Notes"]

        # Build rows — one per BU
        rows = []
        for bu in config["branches"]:
            dropped = set()
            for drop in bu["drops"]:
                for r in get_ranges(drop):
                    dropped.update(range(r[0], r[1] + 1))
            for stub in bu.get("stubs", []):
                for r in get_ranges(stub):
                    dropped.update(range(r[0], r[1] + 1))
            passthrough = trunk_fps - len(dropped)
            fp_list = ", ".join(str(f) for f in sorted(dropped)) if dropped else "—"
            rows.append([bu.get("label", bu["id"]),
                         f"{len(dropped)} ({fp_list})" if len(dropped) <= 8 else f"{len(dropped)} FPs",
                         str(passthrough),
                         bu.get("notes", "")])

        table_h = TITLE_H + ROW_H + len(rows) * ROW_H + PAD

        # Outer box
        box_style = ("rounded=1;whiteSpace=wrap;html=1;fillColor=#ffffff;"
                     "strokeColor=#666666;verticalAlign=top;align=left;"
                     "spacingTop=6;spacingLeft=10;fontSize=11;fontStyle=1;")
        box = ET.SubElement(root, 'mxCell', id="fc_table_box",
                            value="Fibre Count Summary",
                            style=box_style, vertex="1", parent="1")
        ET.SubElement(box, 'mxGeometry', x=str(lx), y=str(ly),
                      width=str(total_w), height=str(table_h),
                      **{'as': 'geometry'})

        def cell_style(bold=False, bg="#e8eaf6"):
            return (f"text;html=1;strokeColor=#aaaaaa;fillColor={bg};"
                    f"align=left;verticalAlign=middle;whiteSpace=wrap;rounded=0;"
                    f"fontSize=10;{'fontStyle=1;' if bold else ''}"
                    f"spacingLeft=4;")

        # Header row
        cx = lx
        for ci, (hdr, cw) in enumerate(zip(headers, COL_W)):
            cell = ET.SubElement(root, 'mxCell', id=f"fc_hdr_{ci}",
                                 value=hdr, style=cell_style(bold=True),
                                 vertex="1", parent="1")
            ET.SubElement(cell, 'mxGeometry',
                          x=str(cx), y=str(ly + TITLE_H),
                          width=str(cw), height=str(ROW_H), **{'as': 'geometry'})
            cx += cw

        # Data rows
        for ri, row in enumerate(rows):
            cx = lx
            row_y = ly + TITLE_H + ROW_H + ri * ROW_H
            bg = "#ffffff" if ri % 2 == 0 else "#f5f5f5"
            for ci, (val, cw) in enumerate(zip(row, COL_W)):
                cell = ET.SubElement(root, 'mxCell', id=f"fc_row_{ri}_{ci}",
                                     value=str(val), style=cell_style(bold=False, bg=bg),
                                     vertex="1", parent="1")
                ET.SubElement(cell, 'mxGeometry',
                              x=str(cx), y=str(row_y),
                              width=str(cw), height=str(ROW_H), **{'as': 'geometry'})
                cx += cw

        return table_h

    # --- TITLE BLOCK (bottom-left, below fibre summary) ---
    def add_title_block(bx=None, by=None, BLOCK_W=500, BLOCK_H=160):
        tb = config.get("title_block", {})
        if not tb.get("enabled", False):
            return
        # Bottom-right: to the right of the EAST node, aligned with trunk top
        if bx is None:
            bx = nodes["EAST"]["x"] + NODE_WIDTH + 40
        if by is None:
            by = nodes["WEST"]["y"]

        # Outer border
        border_style = ("rounded=0;whiteSpace=wrap;html=1;"
                        "fillColor=#ffffff;strokeColor=#333333;strokeWidth=2;"
                        "verticalAlign=top;align=left;")
        box = ET.SubElement(root, 'mxCell', id="title_block_box",
                            value="", style=border_style,
                            vertex="1", parent="1")
        ET.SubElement(box, 'mxGeometry', x=str(bx), y=str(by),
                      width=str(BLOCK_W), height=str(BLOCK_H),
                      **{'as': 'geometry'})

        def tb_cell(cid, val, x, y, w, h, bold=False, size=10, bg="#ffffff", align="left"):
            style = (f"text;html=1;strokeColor=#cccccc;fillColor={bg};"
                     f"align={align};verticalAlign=middle;whiteSpace=wrap;rounded=0;"
                     f"fontSize={size};{'fontStyle=1;' if bold else ''}spacingLeft=4;")
            cell = ET.SubElement(root, 'mxCell', id=cid, value=val,
                                 style=style, vertex="1", parent="1")
            ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y),
                          width=str(w), height=str(h), **{'as': 'geometry'})

        ROW = 26
        # Title row — system name
        tb_cell("tb_sys",    tb.get("system_name", config.get("system_name", "")),
                bx, by, BLOCK_W - 100, ROW + 4, bold=True, size=13, bg="#dce3f0", align="center")
        # Logo placeholder (right of title)
        logo_style = ("rounded=0;whiteSpace=wrap;html=1;"
                      "fillColor=#f5f5f5;strokeColor=#cccccc;"
                      "align=center;verticalAlign=middle;fontSize=9;fontColor=#aaaaaa;")
        logo_cell = ET.SubElement(root, 'mxCell', id="tb_logo",
                                  value=tb.get("logo_text", "LOGO"),
                                  style=logo_style, vertex="1", parent="1")
        ET.SubElement(logo_cell, 'mxGeometry',
                      x=str(bx + BLOCK_W - 100), y=str(by),
                      width="100", height=str(ROW + 4), **{'as': 'geometry'})

        # Field rows
        fields = [
            ("Revision",         tb.get("revision", "")),
            ("Date",             tb.get("date", "")),
            ("Designer",         tb.get("designer", "")),
            ("Total Throughput", tb.get("total_throughput", "")),
        ]
        LABEL_W = 120
        for fi, (label, val) in enumerate(fields):
            row_y = by + ROW + 4 + fi * ROW
            tb_cell(f"tb_lbl_{fi}", label,
                    bx, row_y, LABEL_W, ROW, bold=True, bg="#f0f0f0")
            tb_cell(f"tb_val_{fi}", val,
                    bx + LABEL_W, row_y, BLOCK_W - LABEL_W, ROW)

    # --- FIBRE SUMMARY PLACEMENT ---
    # Place it below the switch legend (reuse measured ly + legend heights)
    COLOR_LEGEND_HEIGHT = 30
    COLOR_ROW_H         = 28
    H_PAD               = 12
    lx_base = int(nodes["WEST"]["x"])
    ly_base = int(nodes["WEST"]["y"] + TRUNK_NODE_HEIGHT + 60)
    colors_config = config["trunk"].get("colors", [])
    if colors_config:
        covered = set()
        for rule in colors_config:
            covered.update(range(max(1, rule["fp_range"][0]),
                                 min(trunk_fps, rule["fp_range"][1]) + 1))
        default_count = 1 if any(i not in covered for i in range(1, trunk_fps + 1)) else 0
        n_entries = default_count + len(set(r["color"] for r in colors_config))
        color_box_h = COLOR_LEGEND_HEIGHT + n_entries * COLOR_ROW_H + H_PAD
    else:
        color_box_h = 0
    SW_LEGEND_H = 250   # fixed height of the switch positions box
    gap_after_legend = 20
    summary_y = ly_base + color_box_h + (20 if color_box_h else 0) + SW_LEGEND_H + gap_after_legend
    fc_table_h = add_fibre_summary(lx_base, summary_y)

    # --- DIAGRAM BORDER + TITLE BLOCK (ordered to solve chicken-and-egg) ---
    # Step 1: measure bounding box of all content placed so far (no title block yet)
    BORDER_PAD    = 40
    BORDER_CORNER = 20
    TB_W, TB_H    = 500, 160

    def content_bbox():
        all_x, all_y, all_x2, all_y2 = [], [], [], []
        for cell in root.iter('mxCell'):
            geo = cell.find('mxGeometry')
            if geo is None:
                continue
            if cell.get('vertex') == '1':
                try:
                    ex = float(geo.get('x', 0)); ey = float(geo.get('y', 0))
                    ew = float(geo.get('width', 0)); eh = float(geo.get('height', 0))
                    all_x.append(ex); all_y.append(ey)
                    all_x2.append(ex + ew); all_y2.append(ey + eh)
                except (TypeError, ValueError):
                    pass
            elif cell.get('edge') == '1':
                for pt in geo.findall('mxPoint'):
                    try:
                        px = float(pt.get('x', 0)); py = float(pt.get('y', 0))
                        all_x.append(px); all_y.append(py)
                        all_x2.append(px); all_y2.append(py)
                    except (TypeError, ValueError):
                        pass
        if not all_x:
            return 0, 0, 100, 100
        return min(all_x), min(all_y), max(all_x2), max(all_y2)

    cx1, cy1, cx2, cy2 = content_bbox()

    # Step 2: place title block anchored to bottom-right corner of the future border
    bdr_x  = cx1 - BORDER_PAD
    bdr_y  = cy1 - BORDER_PAD
    bdr_x2 = cx2 + BORDER_PAD
    bdr_y2 = cy2 + BORDER_PAD

    tb = config.get("title_block", {})
    if tb.get("enabled", False):
        # Anchor: right edge of border, bottom edge of border
        tb_x = bdr_x2 - TB_W
        tb_y = bdr_y2 - TB_H
        add_title_block(bx=tb_x, by=tb_y, BLOCK_W=TB_W, BLOCK_H=TB_H)
        # Expand border to include title block (it sits inside the border footprint
        # since we anchored to its inner-right/bottom)

    # Step 3: re-measure after title block is added, then draw border
    cx1, cy1, cx2, cy2 = content_bbox()
    bdr_x  = cx1 - BORDER_PAD
    bdr_y  = cy1 - BORDER_PAD
    bdr_x2 = cx2 + BORDER_PAD
    bdr_y2 = cy2 + BORDER_PAD
    bdr_w  = bdr_x2 - bdr_x
    bdr_h  = bdr_y2 - bdr_y

    bdr_style = (
        f"rounded=1;arcSize={max(1, int(100 * BORDER_CORNER / min(bdr_w, bdr_h)))};"
        "whiteSpace=wrap;html=1;fillColor=none;"
        "strokeColor=#333333;strokeWidth=3;dashed=0;"
        "verticalAlign=top;align=left;pointerEvents=0;"
    )
    bdr_cell = ET.SubElement(root, 'mxCell', id="diagram_border",
                             value="", style=bdr_style, vertex="1", parent="1")
    ET.SubElement(bdr_cell, 'mxGeometry',
                  x=str(round(bdr_x, 1)), y=str(round(bdr_y, 1)),
                  width=str(round(bdr_w, 1)), height=str(round(bdr_h, 1)),
                  **{'as': 'geometry'})

    # --- SERIALIZE ---
    ET.indent(tree := ET.ElementTree(mxfile), space="\t", level=0)
    buffer = io.BytesIO()
    tree.write(buffer, encoding="utf-8", xml_declaration=True)
    return buffer.getvalue()


def generate_from_json(json_filepath, output_filepath):
    with open(json_filepath, 'r') as f:
        config = json.load(f)
    xml_bytes = generate_from_config(config)
    with open(output_filepath, 'wb') as f:
        f.write(xml_bytes)


if __name__ == "__main__":
    generate_from_json("temp_payload.json", "output_topology.drawio")