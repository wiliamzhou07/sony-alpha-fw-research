import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.util.task.ConsoleTaskMonitor;
import java.io.*;

public class DumpDecomp extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outpath = args[0];
        int maxf = args.length > 1 ? Integer.parseInt(args[1]) : 100000;
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
        PrintWriter out = new PrintWriter(new BufferedWriter(new FileWriter(outpath)));
        int n = 0;
        while (it.hasNext() && n < maxf) {
            Function f = it.next();
            try {
                DecompileResults res = di.decompileFunction(f, 90, monitor);
                if (res.decompileCompleted()) {
                    out.println("// ==== " + f.getName() + " @ " + f.getEntryPoint() + " ====");
                    out.println(res.getDecompiledFunction().getC());
                    out.println();
                    n++;
                }
            } catch (Exception e) {
                // skip pathological functions
            }
        }
        out.close();
        println("DUMP_DONE " + n + " functions -> " + outpath);
    }
}
