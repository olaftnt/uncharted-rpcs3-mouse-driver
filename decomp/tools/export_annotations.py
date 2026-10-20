#!/usr/bin/env python3
"""
Export the user-made annotations of the Uncharted 3 Ghidra project into annotations.json.

Reads a running Ghidra through the GhidraMCP HTTP server (default http://127.0.0.1:8089).
Exports only what a person added - names, comments, prototypes, renamed variables, structs -
and never any bytes, instructions or decompiled code of the game.

  python tools/export_annotations.py [--server http://127.0.0.1:8089] [--out annotations.json]
"""

import re
import json
import argparse
import urllib.parse
import urllib.request
from pathlib import Path

EXPECTED = {
    "title": "Uncharted 3: Drake's Deception",
    "version": "1.19 (BCES01175 and other 1.19 serials)",
    "file": "EBOOT.elf (decrypted EBOOT.BIN)",
    "size": 18778872,
    "md5": "94cd514e7490e53ec4a39122611c5606",
    "sha256": "aac4faa63ab1387e8aaa0b8e9e80ee87ac4ae61e0b40292f7aa7401df7b3f50a",
    "rpcs3_ppu_hash": "PPU-02a88c3c6cd415b0bb81f1606bc743835881a4ba",
    "ghidra_language": "PowerPC:BE:64:A2ALT-32addr",
}
STRUCTS = ("PlayerInputState", "RawGamepadInput")

DEFAULT_FUNC = re.compile(r"^(\.opd\.)?(thunk_)?(FUN|LAB|SUB|DAT|switchD|caseD|entry)_?[0-9a-fA-F]*$")
SDK_FUNC = re.compile(r"^(\.opd\.)?(syscall_|cell|sce|sys_|_sys_|_cell|_sce)")
DEFAULT_LABEL = re.compile(r"^(DAT|PTR|LAB|FUN|s_|u_|switchD|caseD|\.|_elf|Elf|tocPtr|__|sys_process_|FNID_|VNID_|"
                           r"_scelib|_sce|sceModule|\w+_func_(nid|address)_table|\w+_var_(nid|address)_table|\w+_stub)")
DEFAULT_VAR = re.compile(r"^([a-z]{1,3}Var\d+|in_\w+|local_\w+|param_\d+|extraout_\w+|unaff_\w+|"
                         r"[a-z]{1,3}Stack_?\w+|in_stack_\w+|stack0x\w+)$")
# working notes start with a "[Author YYYY-MM-DD]" session tag; keep only the note itself
NOTE_TAG = re.compile(r"\[[A-Za-z]+ \d{4}-\d{2}-\d{2}\]\s*")


class Ghidra:
    def __init__(self, base):
        self.base = base.rstrip("/") + "/"

    def get(self, endpoint, **params):
        url = self.base + endpoint + ("?" + urllib.parse.urlencode(params) if params else "")
        body = urllib.request.urlopen(url, timeout=300).read().decode("utf-8", "replace")
        try:
            return json.loads(body)
        except ValueError:
            return body


def clean(text):
    return NOTE_TAG.sub("", text or "").strip()


def struct_fields(layout_text):
    size = int(re.search(r"Size:\s*(\d+)", layout_text).group(1))
    fields = []
    for m in re.finditer(r"^\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*(\S+)\s*$", layout_text, re.M):
        fields.append({"offset": int(m.group(1)), "size": int(m.group(2)), "type": m.group(3), "name": m.group(4)})
    return {"size": size, "fields": fields}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:8089")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "annotations.json"))
    a = ap.parse_args()
    gh = Ghidra(a.server)

    globals_ = gh.get("list_globals", offset=0, limit=1000000).splitlines()
    loader_names = {m.group(1) for line in globals_ if (m := re.match(r"^FNID_(\S+) @", line))}

    functions = []
    for f in gh.get("list_functions_enhanced", offset=0, limit=1000000)["functions"]:
        name = f["name"]
        if DEFAULT_FUNC.match(name) or SDK_FUNC.match(name) or name in loader_names:
            continue
        d = gh.get("get_function_documentation", address="0x" + f["address"])
        entry = {"address": f["address"], "name": name}
        if clean(d.get("plate_comment")):
            entry["plate_comment"] = clean(d["plate_comment"])
        if d.get("return_type") not in (None, "undefined") or d.get("parameters"):
            entry["return_type"] = d.get("return_type") or "undefined"
            entry["parameters"] = [{"name": p["name"], "type": p["type"]} for p in d.get("parameters", [])]
        comments = []
        for c in d.get("comments", []):
            for kind in ("pre_comment", "eol_comment", "post_comment", "plate_comment", "repeatable_comment"):
                if clean(c.get(kind)):
                    comments.append({"offset": c["relative_offset"], "type": kind.replace("_comment", ""),
                                     "text": clean(c[kind])})
        if comments:
            entry["comments"] = comments
        variables = [{"name": v["name"], "type": v["type"], "storage": v["storage"]}
                     for v in d.get("local_variables", []) if not DEFAULT_VAR.match(v["name"])]
        if variables:
            entry["variables"] = variables
        functions.append(entry)

    labels = []
    for line in globals_:
        m = re.match(r"^(\S+) @ ([0-9a-fA-F]+) \[Label\]", line)
        if m and not DEFAULT_LABEL.match(m.group(1)):
            labels.append({"address": m.group(2), "name": m.group(1)})

    structs = {s: struct_fields(gh.get("get_struct_layout", struct_name=s)) for s in STRUCTS}

    out = {"format": 1, "program": EXPECTED, "structs": structs, "functions": functions, "labels": labels}
    text = json.dumps(out, indent=2, ensure_ascii=False)
    Path(a.out).write_text(text + "\n", encoding="utf-8", newline="\n")
    print(f"{len(functions)} functions, {len(labels)} labels, {len(structs)} structs -> {a.out}")


if __name__ == "__main__":
    main()
