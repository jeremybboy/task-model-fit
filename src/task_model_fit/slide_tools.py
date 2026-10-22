"""Bounded native PPTX edits and a simplified preview for the included fixture.

This is deliberately not a general PowerPoint importer or renderer.
"""
from __future__ import annotations

import copy
import hashlib
import html
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)
EMU = 9525
SLIDE = "ppt/slides/slide1.xml"


def tag(name):
    prefix, local = name.split(":")
    return "{" + NS[prefix] + "}" + local


def sub(parent, qualified_name, **attributes):
    return ET.SubElement(parent, tag(qualified_name), {k: str(v) for k, v in attributes.items()})


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rgb(parent, path, default):
    value = parent.find(path, NS)
    return "#" + value.get("val") if value is not None else default


def inspect(path):
    with zipfile.ZipFile(path) as z:
        slide = ET.fromstring(z.read(SLIDE))
        size = ET.fromstring(z.read("ppt/presentation.xml")).find("p:sldSz", NS)
    result = {"width": round(int(size.get("cx")) / EMU, 3),
              "height": round(int(size.get("cy")) / EMU, 3),
              "background": _rgb(slide, "p:cSld/p:bg/p:bgPr/a:solidFill/a:srgbClr", "#000000"),
              "shapes": []}
    for shape in slide.findall("p:cSld/p:spTree/p:sp", NS):
        info = shape.find("p:nvSpPr/p:cNvPr", NS)
        transform = shape.find("p:spPr/a:xfrm", NS)
        if info is None or transform is None:
            raise ValueError("The fixture contains an unsupported object.")
        offset, extent = transform.find("a:off", NS), transform.find("a:ext", NS)
        props = shape.find("p:txBody/a:p/a:r/a:rPr", NS)
        if props is None:
            props = shape.find("p:txBody/a:p/a:pPr/a:defRPr", NS)
        if props is None:
            props = ET.Element("placeholder")
        body = shape.find("p:txBody/a:bodyPr", NS)
        body = body if body is not None else ET.Element("placeholder")
        result["shapes"].append({
            "id": info.get("name"), "native_id": info.get("id"),
            "x": round(int(offset.get("x")) / EMU, 3),
            "y": round(int(offset.get("y")) / EMU, 3),
            "width": round(int(extent.get("cx")) / EMU, 3),
            "height": round(int(extent.get("cy")) / EMU, 3),
            "fill": _rgb(shape, "p:spPr/a:solidFill/a:srgbClr", None),
            "text": "\n".join("".join(n.text or "" for n in paragraph.findall(".//a:t", NS))
                                for paragraph in shape.findall("p:txBody/a:p", NS)),
            "font_size": round(float(props.get("sz", "1800")) / 100 * 96 / 72, 3),
            "text_color": _rgb(props, "a:solidFill/a:srgbClr", "#F4F4F5"),
            "bold": props.get("b") == "1",
            "inset_x": int(body.get("lIns", "91440")) / EMU,
            "inset_y": int(body.get("tIns", "45720")) / EMU,
        })
    return result


def render_svg(state):
    w, h = state["width"], state["height"]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-label="Slide preview">',
             f'<rect width="{w}" height="{h}" fill="{state["background"]}"/>']
    for shape in state["shapes"]:
        x, y, sw, sh = (shape[k] for k in ("x", "y", "width", "height"))
        if shape["fill"]:
            parts.append(f'<rect x="{x}" y="{y}" width="{sw}" height="{sh}" fill="{shape["fill"]}"/>')
        if shape["text"]:
            size = shape["font_size"]
            for index, line in enumerate(shape["text"].splitlines()):
                parts.append(f'<text x="{x + shape["inset_x"]}" y="{y + shape["inset_y"] + size * (0.85 + index * 1.2)}" '
                             f'font-family="Arial, sans-serif" font-size="{size}" font-weight="{700 if shape["bold"] else 400}" '
                             f'fill="{shape["text_color"]}">{html.escape(line)}</text>')
    return "".join(parts) + "</svg>"


def _color(value):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        raise ValueError("A color must be a six-digit hex value.")
    return value[1:].upper()


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError("Shape geometry must use finite numbers.")
    return float(value)


def _find_shape(slide, name):
    for shape in slide.findall("p:cSld/p:spTree/p:sp", NS):
        info = shape.find("p:nvSpPr/p:cNvPr", NS)
        if info.get("name") == name:
            return shape
    raise ValueError("The requested shape does not exist.")


def apply(source, destination, operation):
    kind = operation.get("op")
    if kind not in ("set_background", "move_shape", "add_box", "no_change"):
        raise ValueError("Unsupported slide operation.")
    if kind == "no_change":
        Path(destination).write_bytes(Path(source).read_bytes())
        return
    with zipfile.ZipFile(source) as archive:
        entries = [(entry, archive.read(entry.filename)) for entry in archive.infolist()]
    slide = ET.fromstring(dict((e.filename, data) for e, data in entries)[SLIDE])
    if kind == "set_background":
        color = _color(operation.get("color"))
        common = slide.find("p:cSld", NS)
        previous = common.find("p:bg", NS)
        if previous is not None:
            common.remove(previous)
        bg = ET.Element(tag("p:bg"))
        sub(sub(sub(bg, "p:bgPr"), "a:solidFill"), "a:srgbClr", val=color)
        common.insert(0, bg)
    else:
        state = inspect(source)
        x, y = _number(operation.get("x")), _number(operation.get("y"))
        if kind == "move_shape":
            shape = _find_shape(slide, operation.get("shape_id"))
            geometry = next(s for s in state["shapes"] if s["id"] == operation["shape_id"])
            sw, sh = geometry["width"], geometry["height"]
        else:
            sw, sh = _number(operation.get("width")), _number(operation.get("height"))
        if x < 0 or y < 0 or sw <= 0 or sh <= 0 or x + sw > state["width"] or y + sh > state["height"]:
            raise ValueError("The requested shape would extend outside the slide.")
        if kind == "move_shape":
            offset = shape.find("p:spPr/a:xfrm/a:off", NS)
            offset.set("x", str(round(x * EMU)))
            offset.set("y", str(round(y * EMU)))
        else:
            text = operation.get("text")
            if not isinstance(text, str) or len(text) > 120 or any(ord(c) < 32 for c in text):
                raise ValueError("Box text must be at most 120 printable characters.")
            color = _color(operation.get("color"))
            tree = slide.find("p:cSld/p:spTree", NS)
            ident = max(int(n.get("id")) for n in tree.findall(".//p:cNvPr", NS)) + 1
            shape = sub(tree, "p:sp")
            nv = sub(shape, "p:nvSpPr")
            sub(nv, "p:cNvPr", id=ident, name=f"added-box-{ident}")
            sub(nv, "p:cNvSpPr")
            sub(nv, "p:nvPr")
            props = sub(shape, "p:spPr")
            transform = sub(props, "a:xfrm")
            sub(transform, "a:off", x=round(x * EMU), y=round(y * EMU))
            sub(transform, "a:ext", cx=round(sw * EMU), cy=round(sh * EMU))
            sub(sub(props, "a:prstGeom", prst="rect"), "a:avLst")
            sub(sub(props, "a:solidFill"), "a:srgbClr", val=color)
            sub(sub(props, "a:ln", w=0), "a:noFill")
            body = sub(shape, "p:txBody")
            sub(body, "a:bodyPr", lIns=round(18 * EMU), tIns=round(16 * EMU))
            sub(body, "a:lstStyle")
            paragraph = sub(body, "a:p")
            run = sub(paragraph, "a:r")
            run_props = sub(run, "a:rPr", lang="en-US", sz=2000)
            sub(sub(run_props, "a:solidFill"), "a:srgbClr", val="14332B")
            sub(run_props, "a:latin", typeface="Arial")
            sub(run, "a:t").text = text
    updated = ET.tostring(slide, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry, data in entries:
            archive.writestr(entry, updated if entry.filename == SLIDE else data)


def overlap(a, b):
    return (a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"]
            and a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"])


def audit(before, after, task):
    old = {s["id"]: s for s in before["shapes"]}
    new = {s["id"]: s for s in after["shapes"]}
    checks = []
    if task == "background":
        checks.append(("Background is #4A5054", after["background"].upper() == "#4A5054"))
        preserved = before["shapes"] == after["shapes"]
    elif task == "box":
        added = [s for s in after["shapes"] if s["id"] not in old]
        checks.append(("One box says Next step in the bottom-right corner",
                       len(added) == 1 and added[0]["text"] == "Next step"
                       and added[0]["x"] >= after["width"] * .65
                       and added[0]["y"] >= after["height"] * .7
                       and added[0]["fill"] == "#A7F3D0"))
        preserved = before["background"] == after["background"] and all(new.get(k) == v for k, v in old.items())
    elif task == "overlap":
        square = new.get("accent-square")
        text_shapes = [s for s in after["shapes"] if s["text"]]
        checks.append(("Square is clear of all text boxes", square is not None and all(not overlap(square, s) for s in text_shapes)))
        expected = copy.deepcopy(before)
        if square:
            for shape in expected["shapes"]:
                if shape["id"] == "accent-square":
                    shape["x"], shape["y"] = square["x"], square["y"]
        preserved = expected == after
    else:
        checks.append(("Slide is unchanged", before == after))
        preserved = before == after
    checks.append(("Unrelated content and formatting preserved", preserved))
    return {"passed": all(value for _, value in checks),
            "checks": [{"label": name, "passed": bool(value)} for name, value in checks],
            "scope": "Structural checks for the included slide; native PowerPoint visual review remains manual."}


def tool_test_plan(task, state):
    blank = dict(shape_id=None, x=None, y=None, width=None, height=None, color=None, text=None)
    if task == "background":
        op = dict(blank, op="set_background", color="#4A5054")
    elif task == "box":
        op = dict(blank, op="add_box", x=960, y=580, width=240, height=80, color="#A7F3D0", text="Next step")
    elif task == "overlap":
        square = next(s for s in state["shapes"] if s["id"] == "accent-square")
        occupied = [s for s in state["shapes"] if s["text"]]
        point = next(({"x": x, "y": y} for y in (400, 500, 580) for x in (84, 400, 700)
                      if all(not overlap(dict(square, x=x, y=y), t) for t in occupied)), None)
        if point is None:
            raise ValueError("No free position is available in the fixture.")
        op = dict(blank, op="move_shape", shape_id="accent-square", **point)
    else:
        op = dict(blank, op="no_change")
    return {"operations": [op], "note": "Deterministic slide-tool test. No model was called."}
