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

    # --- NODE LAYOUT ---
    nodes["WEST"] = {
        "x": 50, "y": 50, "label": config["trunk"]["west_node"],
        "height": TRUNK_NODE_HEIGHT, "node_type": "trunk"
    }
    current_col_x = 50 + NODE_WIDTH + LANE_WIDTH

    for bu in config["branches"]:
        switch_pos  = bu.get("switch_position", "default")
        bu_inactive = (switch_pos == "pos1")

        nodes[bu["id"]] = {
            "x": current_col_x, "y": 50, "label": bu["label"],
            "height": TRUNK_NODE_HEIGHT, "node_type": "trunk"
        }
        current_drop_y = 50 + TRUNK_NODE_HEIGHT + DROP_DEPTH

        temp_fp_x  = {}
        temp_shift = 0
        is_1x2     = bu.get("switch_type") == "1x2"

        for drop in bu["drops"]:
            for r in get_ranges(drop):
                is_new_bundle = False
                for i in range(r[0], r[1] + 1):
                    if i not in temp_fp_x:
                        if is_1x2:
                            temp_fp_x[i] = [current_col_x + temp_shift + 10,
                                            current_col_x + temp_shift + 10 + LINE_GAP]
                            temp_shift += LINE_GAP * 2
                        else:
                            temp_fp_x[i] = [current_col_x + temp_shift + 10]
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
    trunk_end_x = {i: nodes["EAST"]["x"] for i in range(1, trunk_fps + 1)}
    for bu in config["branches"]:
        if bu.get("routing_mode") == "fixed":
            bu_right_x = nodes[bu["id"]]["x"] + NODE_WIDTH
            for drop in bu["drops"]:
                for r in get_ranges(drop):
                    for i in range(r[0], r[1] + 1):
                        if trunk_end_x[i] == nodes["EAST"]["x"]:
                            trunk_end_x[i] = bu_right_x

    for i in range(1, trunk_fps + 1):
        y_off = nodes["WEST"]["y"] + (i * FP_SPACING) + 30
        end_x = trunk_end_x[i]
        add_line(f"fp_{i}_trunk", nodes["WEST"]["x"] + NODE_WIDTH, y_off,
                 end_x, y_off, fp_colors[i])
        add_label(i, nodes["WEST"]["x"] + NODE_WIDTH - 20, y_off)
        if end_x >= nodes["EAST"]["x"]:
            add_label(i, nodes["EAST"]["x"] + 10, y_off)

    # --- RENDER DROP ROUTING ---
    for bu in config["branches"]:
        switch_pos = bu.get("switch_position", "default")

        fp_x_coords = {}
        cur_shift   = 0
        is_1x2      = bu.get("switch_type") == "1x2"

        for drop in bu["drops"]:
            for r in get_ranges(drop):
                is_new_bundle = False
                for i in range(r[0], r[1] + 1):
                    if i not in fp_x_coords:
                        if is_1x2:
                            x1 = nodes[bu["id"]]["x"] + cur_shift + 10
                            fp_x_coords[i] = [x1, x1 + LINE_GAP]
                            cur_shift += LINE_GAP * 2
                        else:
                            fp_x_coords[i] = [nodes[bu["id"]]["x"] + cur_shift + 10]
                            cur_shift += LINE_GAP
                        is_new_bundle = True
                if is_new_bundle:
                    cur_shift += BUNDLE_GAP

        if switch_pos == "pos1":
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