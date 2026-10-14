// Names unnamed functions after the strings they use: "Class::method" names from
// assertions and "name: ..." trace messages. Functions that use more than one
// candidate are left alone and listed.
//@category JetSet

import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Namespace;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.SourceType;

public class NameFromStrings extends GhidraScript {
    private static final Pattern QUALIFIED = Pattern.compile("^([A-Za-z_]\\w*)::(~?[A-Za-z_]\\w*)$");
    private static final Pattern TRACE = Pattern.compile("^([A-Za-z_]\\w{4,})(?:: | - |\\()");

    @Override
    protected void run() throws Exception {
        Map<Function, Set<String>> found = new HashMap<>();
        DataIterator strings = currentProgram.getListing().getDefinedData(true);
        while (strings.hasNext()) {
            Data data = strings.next();
            if (!data.hasStringValue()) {
                continue;
            }
            String name = candidate(String.valueOf(data.getValue()));
            if (name == null) {
                continue;
            }
            ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(data.getAddress());
            while (refs.hasNext()) {
                Reference ref = refs.next();
                Function function = getFunctionContaining(ref.getFromAddress());
                if (function != null && function.getName().startsWith("FUN_")) {
                    found.computeIfAbsent(function, k -> new TreeSet<>()).add(name);
                }
            }
        }

        int renamed = 0;
        int ambiguous = 0;
        for (Map.Entry<Function, Set<String>> e : found.entrySet()) {
            Function function = e.getKey();
            if (e.getValue().size() != 1) {
                println("ambiguous " + function.getEntryPoint() + " " + e.getValue());
                ambiguous++;
                continue;
            }
            String name = e.getValue().iterator().next();
            if (apply(function, name)) {
                println("named " + function.getEntryPoint() + " " + name);
                renamed++;
            }
        }
        println("named " + renamed + " functions, " + ambiguous + " ambiguous");
    }

    private String candidate(String text) {
        Matcher m = QUALIFIED.matcher(text);
        if (m.matches()) {
            return text;
        }
        m = TRACE.matcher(text);
        if (m.find() && looksLikeName(m.group(1))) {
            return m.group(1);
        }
        return null;
    }

    private boolean looksLikeName(String s) {
        boolean lower = !s.equals(s.toUpperCase());
        boolean upper = s.substring(1).chars().anyMatch(Character::isUpperCase);
        return s.indexOf('_') > 0 || (lower && upper);
    }

    private boolean apply(Function function, String name) {
        try {
            int split = name.indexOf("::");
            if (split > 0) {
                Namespace ns = currentProgram.getSymbolTable().getOrCreateNameSpace(
                        currentProgram.getGlobalNamespace(), name.substring(0, split), SourceType.ANALYSIS);
                function.setParentNamespace(ns);
                function.setName(name.substring(split + 2), SourceType.ANALYSIS);
            } else {
                function.setName(name, SourceType.ANALYSIS);
            }
            return true;
        } catch (Exception ex) {
            try {
                function.setName(name.replace("::", "_") + "_" + function.getEntryPoint(), SourceType.ANALYSIS);
                return true;
            } catch (Exception again) {
                return false;
            }
        }
    }
}
