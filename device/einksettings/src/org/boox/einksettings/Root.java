package org.boox.einksettings;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.TimeUnit;

/**
 * Runs a shell script as root through Magisk su. persist.boox.* props fall under SELinux
 * default_prop, which no app domain may set, so even a system app needs root here.
 * Call only from a background thread: the first call can wait on Magisk's grant prompt.
 */
final class Root {
    /** Magisk on this device exposes su at /debug_ramdisk/su. "su" covers a PATH install. */
    private static final String[] SU = {"/debug_ramdisk/su", "su"};

    static final class Result {
        final int exit;
        final String out;
        Result(int exit, String out) { this.exit = exit; this.out = out; }
        boolean ok() { return exit == 0; }
    }

    private Root() {}

    static Result run(String script) {
        IOException last = null;
        for (String su : SU) {
            Process p;
            try {
                p = new ProcessBuilder(su).redirectErrorStream(true).start();
            } catch (IOException e) {
                last = e;
                continue;   // binary absent: try the next path
            }
            try {
                OutputStream in = p.getOutputStream();
                in.write((script + "\nexit\n").getBytes(StandardCharsets.UTF_8));
                in.close();
                String out = readAll(p.getInputStream());
                if (!p.waitFor(60, TimeUnit.SECONDS)) {
                    p.destroy();
                    return new Result(-2, "su timed out");
                }
                return new Result(p.exitValue(), out);
            } catch (IOException e) {
                p.destroy();
                return new Result(-1, "su failed: " + e.getMessage());
            } catch (InterruptedException e) {
                p.destroy();
                Thread.currentThread().interrupt();
                return new Result(-1, "interrupted");
            }
        }
        return new Result(-1, "no su binary: " + (last == null ? "" : last.getMessage()));
    }

    private static String readAll(InputStream s) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while ((n = s.read(buf)) > 0) b.write(buf, 0, n);
        return b.toString("UTF-8");
    }
}
