// Prepares the unpacked executable image for analysis: one memory block per PE
// section, the function table, and names for the import slots and thunks.
//
// Import image.bin as a raw binary at 0x82000000 (PowerPC:BE:64:A2ALT-32addr), then
// run this before auto analysis:
//   -preScript SetupImage.java functions.tsv imports.tsv
//@category JetSet

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.SourceType;

public class SetupImage extends GhidraScript {
    private static final long BASE = 0x82000000L;
    private static final long ENTRY = 0x8232F750L;
    private static final long IMAGE_FLAG_EXECUTE = 0x20000000L;
    private static final long IMAGE_FLAG_WRITE = 0x80000000L;

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            printerr("usage: SetupImage.java functions.tsv imports.tsv");
            return;
        }
        splitSections();
        int names = nameImports(args[1]);
        int funcs = addFunctions(args[0]);
        println("sections: " + currentProgram.getMemory().getBlocks().length
                + ", import names: " + names + ", functions: " + funcs);
    }

    private void splitSections() throws Exception {
        Memory memory = currentProgram.getMemory();
        byte[] header = new byte[0x400];
        memory.getBytes(toAddr(BASE), header);
        ByteBuffer buf = ByteBuffer.wrap(header).order(ByteOrder.LITTLE_ENDIAN);
        int pe = buf.getInt(0x3C);
        int count = buf.getShort(pe + 6) & 0xFFFF;
        int table = pe + 24 + (buf.getShort(pe + 20) & 0xFFFF);

        memory.getBlock(toAddr(BASE)).setName("headers");
        for (int i = 0; i < count; i++) {
            int at = table + i * 40;
            String name = new String(header, at, 8, StandardCharsets.US_ASCII).split("\0")[0];
            long rva = buf.getInt(at + 12) & 0xFFFFFFFFL;
            long flags = buf.getInt(at + 36) & 0xFFFFFFFFL;
            Address start = toAddr(BASE + rva);
            MemoryBlock block = memory.getBlock(start);
            if (!block.getStart().equals(start)) {
                memory.split(block, start);
                block = memory.getBlock(start);
            }
            block.setName(name);
            block.setRead(true);
            block.setWrite((flags & IMAGE_FLAG_WRITE) != 0);
            block.setExecute((flags & IMAGE_FLAG_EXECUTE) != 0);
        }
    }

    private List<String[]> rows(String path) throws Exception {
        List<String[]> out = new ArrayList<>();
        List<String> lines = Files.readAllLines(Paths.get(path));
        for (int i = 1; i < lines.size(); i++) {
            if (!lines.get(i).isBlank()) {
                out.add(lines.get(i).split("\t"));
            }
        }
        return out;
    }

    private int nameImports(String path) throws Exception {
        int named = 0;
        for (String[] row : rows(path)) {
            Address addr = toAddr(Long.parseLong(row[0], 16));
            String lib = row[2].replaceAll("\\.(xex|exe)$", "");
            String base = lib + "_" + row[3];
            if (row[1].equals("slot")) {
                createLabel(addr, "__imp_" + base, true, SourceType.IMPORTED);
            } else {
                disassemble(addr);
                if (createFunction(addr, base) == null) {
                    createLabel(addr, base, true, SourceType.IMPORTED);
                }
            }
            named++;
        }
        return named;
    }

    private int addFunctions(String path) throws Exception {
        int made = 0;
        for (String[] row : rows(path)) {
            Address addr = toAddr(Long.parseLong(row[0], 16));
            if (getFunctionAt(addr) != null) {
                continue;
            }
            disassemble(addr);
            if (createFunction(addr, null) != null) {
                made++;
            }
        }
        Address entry = toAddr(ENTRY);
        if (getFunctionAt(entry) == null) {
            disassemble(entry);
            createFunction(entry, "entry");
        }
        addEntryPoint(entry);
        return made;
    }
}
