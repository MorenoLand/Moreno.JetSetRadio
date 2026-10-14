// Turns off the analyzer that removes code after calls it believes never return.
// On this image it deletes whole functions that follow short stubs.
//
// The setting is stored in the program and only used by a later run, so run this
// with -noanalysis and start the analysis in a second run (-process image.bin).
//@category JetSet

import ghidra.app.script.GhidraScript;

public class AnalysisOptions extends GhidraScript {
    @Override
    protected void run() throws Exception {
        setAnalysisOption(currentProgram, "Non-Returning Functions - Discovered", "false");
    }
}
