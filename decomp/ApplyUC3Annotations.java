// Applies annotations.json (function names, prototypes, comments, variable names, labels and
// structs) to your own Uncharted 3 1.19 EBOOT.elf. Checks the executable hash first.
//
// GUI: put this file and annotations.json in a script directory, run from the Script Manager.
// Headless: analyzeHeadless <proj_dir> <proj> -import EBOOT.elf -postScript ApplyUC3Annotations.java [json] [force]
// @category UC3

import java.io.File;
import java.io.FileReader;
import java.util.ArrayList;
import java.util.List;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.CategoryPath;
import ghidra.program.model.data.DataType;
import ghidra.program.model.data.DataTypeConflictHandler;
import ghidra.program.model.data.DataTypeManager;
import ghidra.program.model.data.StructureDataType;
import ghidra.program.model.data.Undefined;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Parameter;
import ghidra.program.model.listing.ParameterImpl;
import ghidra.program.model.pcode.HighFunction;
import ghidra.program.model.pcode.HighFunctionDBUtil;
import ghidra.program.model.pcode.HighSymbol;
import ghidra.program.model.symbol.SourceType;
import ghidra.util.data.DataTypeParser;
import ghidra.util.data.DataTypeParser.AllowedDataTypes;

public class ApplyUC3Annotations extends GhidraScript {

    private DataTypeManager dtm;
    private DataTypeParser parser;
    private int functions, comments, variables, labels, structs, problems;

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        boolean force = false;
        File json = null;
        for (String a : args) {
            if (a.equalsIgnoreCase("force")) force = true;
            else json = new File(a);
        }
        if (json == null) json = new File(getSourceFile().getParentFile().getFile(false), "annotations.json");
        if (!json.isFile()) {
            if (isRunningHeadless()) { printerr("annotations.json not found: " + json); return; }
            json = askFile("Select annotations.json", "Apply");
        }
        JsonObject root;
        try (FileReader r = new FileReader(json, java.nio.charset.StandardCharsets.UTF_8)) {
            root = JsonParser.parseReader(r).getAsJsonObject();
        }

        JsonObject prog = root.getAsJsonObject("program");
        String sha = currentProgram.getExecutableSHA256();
        String md5 = currentProgram.getExecutableMD5();
        boolean match = prog.get("sha256").getAsString().equalsIgnoreCase(sha)
                || prog.get("md5").getAsString().equalsIgnoreCase(md5);
        if (!match) {
            String msg = "This program is not the expected EBOOT.elf.\n  expected SHA-256 " +
                prog.get("sha256").getAsString() + "\n  this program     " + sha;
            if (isRunningHeadless() && !force) { printerr(msg + "\nAdd the 'force' argument to apply anyway."); return; }
            if (!isRunningHeadless() && !askYesNo("Hash mismatch", msg + "\n\nApply anyway?")) return;
        }

        dtm = currentProgram.getDataTypeManager();
        parser = new DataTypeParser(dtm, dtm, null, AllowedDataTypes.ALL);

        applyStructs(root.getAsJsonObject("structs"));
        for (JsonElement e : root.getAsJsonArray("labels")) applyLabel(e.getAsJsonObject());

        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        try {
            for (JsonElement e : root.getAsJsonArray("functions")) {
                monitor.checkCancelled();
                applyFunction(e.getAsJsonObject(), decomp);
            }
        } finally {
            decomp.dispose();
        }
        println(String.format("UC3 annotations: %d functions, %d comments, %d variables, %d labels, %d structs, %d skipped",
            functions, comments, variables, labels, structs, problems));
    }

    private DataType type(String name, int size) {
        if (name == null || name.startsWith("undefined") && !name.contains("*")) {
            return size > 0 ? Undefined.getUndefinedDataType(size) : DataType.DEFAULT;
        }
        try {
            DataType dt = parser.parse(name);
            if (dt != null) return dt;
        } catch (Exception ignored) {
        }
        problems++;
        printerr("unknown type '" + name + "', using undefined");
        return size > 0 ? Undefined.getUndefinedDataType(size) : DataType.DEFAULT;
    }

    private void applyStructs(JsonObject all) {
        for (String name : all.keySet()) {
            JsonObject s = all.getAsJsonObject(name);
            StructureDataType st = new StructureDataType(CategoryPath.ROOT, name, s.get("size").getAsInt(), dtm);
            for (JsonElement fe : s.getAsJsonArray("fields")) {
                JsonObject f = fe.getAsJsonObject();
                int size = f.get("size").getAsInt();
                st.replaceAtOffset(f.get("offset").getAsInt(), type(f.get("type").getAsString(), size), size,
                    f.get("name").getAsString(), null);
            }
            dtm.addDataType(st, DataTypeConflictHandler.REPLACE_HANDLER);
            structs++;
        }
    }

    private void applyLabel(JsonObject l) throws Exception {
        createLabel(toAddr(l.get("address").getAsString()), l.get("name").getAsString(), true, SourceType.USER_DEFINED);
        labels++;
    }

    private void applyFunction(JsonObject f, DecompInterface decomp) throws Exception {
        Address entry = toAddr(f.get("address").getAsString());
        String name = f.get("name").getAsString();
        Function fn = getFunctionAt(entry);
        if (fn == null) {
            disassemble(entry);
            fn = createFunction(entry, name);
        }
        if (fn == null) {
            problems++;
            printerr("no function at " + entry + " for " + name);
            return;
        }
        fn.setName(name, SourceType.USER_DEFINED);
        functions++;

        if (f.has("plate_comment")) {
            setPlateComment(entry, f.get("plate_comment").getAsString());
            comments++;
        }
        if (f.has("comments")) {
            for (JsonElement ce : f.getAsJsonArray("comments")) {
                JsonObject c = ce.getAsJsonObject();
                Address a = entry.add(c.get("offset").getAsLong());
                String text = c.get("text").getAsString();
                switch (c.get("type").getAsString()) {
                    case "pre": setPreComment(a, text); break;
                    case "eol": setEOLComment(a, text); break;
                    case "post": setPostComment(a, text); break;
                    case "plate": setPlateComment(a, text); break;
                    default: continue;
                }
                comments++;
            }
        }
        if (f.has("return_type")) {
            fn.setReturnType(type(f.get("return_type").getAsString(), 0), SourceType.USER_DEFINED);
            List<Parameter> params = new ArrayList<>();
            for (JsonElement pe : f.getAsJsonArray("parameters")) {
                JsonObject p = pe.getAsJsonObject();
                params.add(new ParameterImpl(p.get("name").getAsString(), type(p.get("type").getAsString(), 4),
                    currentProgram));
            }
            fn.replaceParameters(Function.FunctionUpdateType.DYNAMIC_STORAGE_ALL_PARAMS, true,
                SourceType.USER_DEFINED, params.toArray(new Parameter[0]));
        }
        if (f.has("variables")) applyVariables(fn, f.getAsJsonArray("variables"), decomp);
    }

    // Decompiler locals are matched by their storage (register / stack slot / temporary). Several
    // locals can share one storage; they are matched in the decompiler's order, each used once.
    private void applyVariables(Function fn, JsonArray vars, DecompInterface decomp) throws Exception {
        DecompileResults res = decomp.decompileFunction(fn, 60, monitor);
        HighFunction hf = res != null ? res.getHighFunction() : null;
        if (hf == null) {
            problems += vars.size();
            printerr("could not decompile " + fn.getName() + ", variables skipped");
            return;
        }
        List<HighSymbol> locals = new ArrayList<>();
        java.util.Iterator<HighSymbol> it = hf.getLocalSymbolMap().getSymbols();
        while (it.hasNext()) {
            HighSymbol s = it.next();
            if (!s.isParameter() && s.getStorage() != null && s.getStorage().getFirstVarnode() != null) locals.add(s);
        }
        for (JsonElement ve : vars) {
            JsonObject v = ve.getAsJsonObject();
            String storage = v.get("storage").getAsString();
            HighSymbol target = null;
            for (HighSymbol s : locals) {
                if (s.getStorage().getFirstVarnode().toString().equals(storage)) { target = s; break; }
            }
            if (target != null) locals.remove(target);
            if (target == null) {
                problems++;
                printerr(fn.getName() + ": no variable at " + storage + " for " + v.get("name").getAsString());
                continue;
            }
            HighFunctionDBUtil.updateDBVariable(target, v.get("name").getAsString(),
                type(v.get("type").getAsString(), target.getSize()), SourceType.USER_DEFINED);
            variables++;
        }
    }
}
