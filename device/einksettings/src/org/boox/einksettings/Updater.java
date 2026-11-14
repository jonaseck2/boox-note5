package org.boox.einksettings;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

/**
 * On-device glue updates from the public GitHub Releases (tags glue-v<YYYY.MM.DD.N>), the same bundles
 * `booxctl update glue` installs from the Mac. Design: docs/plans/2026-11-14-ota-design.md.
 *
 * Trust: TLS + the owner's GitHub account. The sidecar and manifest hashes catch corrupt or truncated
 * downloads. Only the three known files are accepted. The new module must carry the boot guard, which
 * restores the previous shim after 3 unhealthy boots. Call only from a background thread.
 */
final class Updater {
    static final String API = "https://api.github.com/repos/jonaseck2/boox-note5/releases?per_page=30";
    static final String MODULE = "/data/adb/modules/boox_epdc";
    private static final Pattern VERSION = Pattern.compile("^(\\d{4})\\.(\\d{2})\\.(\\d{2})\\.(\\d{1,2})$");
    private static final String[] FILES = {"libbooxepdc.so", "module/post-fs-data.sh", "module/service.sh"};

    static final class Release {
        final String version, zipUrl, shaUrl;
        Release(String version, String zipUrl, String shaUrl) {
            this.version = version; this.zipUrl = zipUrl; this.shaUrl = shaUrl;
        }
    }

    private Updater() {}

    /** YYYYMMDD*100 + N, or -1 when the string is not a glue version. */
    static long code(String v) {
        Matcher m = v == null ? null : VERSION.matcher(v);
        if (m == null || !m.matches()) return -1;
        return (Long.parseLong(m.group(1)) * 10000 + Long.parseLong(m.group(2)) * 100
                + Long.parseLong(m.group(3))) * 100 + Long.parseLong(m.group(4));
    }

    /** versionCode from the installed module.prop, or -1. */
    static long installedCode() {
        Root.Result r = Root.run("grep '^versionCode=' " + MODULE + "/module.prop");
        if (!r.ok()) return -1;
        Matcher m = Pattern.compile("versionCode=(\\d+)").matcher(r.out);   // su may add other output
        return m.find() ? Long.parseLong(m.group(1)) : -1;
    }

    static Release latest() throws IOException {
        try {
            JSONArray rels = new JSONArray(new String(get(API), StandardCharsets.UTF_8));
            Release best = null;
            for (int i = 0; i < rels.length(); i++) {
                JSONObject r = rels.getJSONObject(i);
                String tag = r.optString("tag_name");
                if (r.optBoolean("draft") || r.optBoolean("prerelease") || !tag.startsWith("glue-v")) continue;
                String v = tag.substring("glue-v".length());
                if (code(v) < 0) continue;
                String zip = null, sha = null;
                JSONArray assets = r.getJSONArray("assets");
                for (int j = 0; j < assets.length(); j++) {
                    JSONObject a = assets.getJSONObject(j);
                    String n = a.optString("name"), u = a.optString("browser_download_url");
                    if (n.equals("boox-glue-" + v + ".zip")) zip = u;
                    if (n.equals("boox-glue-" + v + ".zip.sha256")) sha = u;
                }
                if (zip == null || sha == null) continue;
                if (best == null || code(v) > code(best.version)) best = new Release(v, zip, sha);
            }
            return best;
        } catch (org.json.JSONException e) {
            throw new IOException("bad release list: " + e.getMessage());
        }
    }

    /** Download, verify, stage into dir, install through root. Returns a message; throws on any failure. */
    static String install(Release rel, File dir) throws IOException {
        if (code(rel.version) < 0) throw new IOException("bad version " + rel.version);
        byte[] zip = get(rel.zipUrl);
        String want = new String(get(rel.shaUrl), StandardCharsets.UTF_8).trim().split("\\s+")[0];
        if (!hex(sha256(zip)).equals(want)) throw new IOException("zip does not match its sha256 sidecar");

        Map<String, byte[]> files = new HashMap<>();
        try (ZipInputStream z = new ZipInputStream(new java.io.ByteArrayInputStream(zip))) {
            ZipEntry e;
            while ((e = z.getNextEntry()) != null) files.put(e.getName(), readAll(z));
        }
        byte[] mf = files.get("manifest.json");
        if (mf == null) throw new IOException("no manifest.json");
        try {
            JSONObject m = new JSONObject(new String(mf, StandardCharsets.UTF_8));
            if (m.getInt("format") != 1 || !"glue".equals(m.getString("kind"))
                    || !rel.version.equals(m.getString("version"))) {
                throw new IOException("manifest does not describe glue " + rel.version);
            }
            JSONObject list = m.getJSONObject("files");
            for (String f : FILES) {
                byte[] body = files.get(f);
                if (body == null || !list.has(f)) throw new IOException("bundle lacks " + f);
                if (!hex(sha256(body)).equals(list.getJSONObject(f).getString("sha256"))) {
                    throw new IOException("hash mismatch: " + f);
                }
            }
        } catch (org.json.JSONException e) {
            throw new IOException("bad manifest: " + e.getMessage());
        }
        if (!new String(files.get("module/post-fs-data.sh"), StandardCharsets.UTF_8).contains("boox_boot_count")) {
            throw new IOException("refusing: the new module has no boot guard");
        }

        File stage = new File(dir, "glue-" + rel.version);
        new File(stage, "module").mkdirs();
        for (String f : FILES) {
            try (FileOutputStream o = new FileOutputStream(new File(stage, f))) { o.write(files.get(f)); }
        }
        long vc = code(rel.version);
        String s = stage.getAbsolutePath();
        String script = "set -e\n"
                + "M=" + MODULE + "\n"
                + "L=$M/system/vendor/lib64/libbooxepdc.so\n"
                + "S='" + s + "'\n"
                + "grep -q boox_boot_count $M/post-fs-data.sh   # never update a module without the guard\n"
                + "[ -f $L ] && ! cmp -s $L $S/libbooxepdc.so && cp $L $L.prev\n"
                + "cp $S/libbooxepdc.so $L.new\n"
                + "chmod 644 $L.new\n"
                + "chcon u:object_r:vendor_file:s0 $L.new\n"
                + "mv -f $L.new $L   # never write into the mapped file: rename\n"
                + "cp $S/module/post-fs-data.sh $M/post-fs-data.sh\n"
                + "cp $S/module/service.sh $M/service.sh\n"
                + "chmod 755 $M/post-fs-data.sh $M/service.sh\n"
                + "sed -i 's/^version=.*/version=" + rel.version + "/; s/^versionCode=.*/versionCode=" + vc + "/' $M/module.prop\n"
                + "rm -rf $S\n"
                + "grep '^version=' $M/module.prop\n";
        Root.Result r = Root.run(script);
        if (!r.ok()) throw new IOException("install failed: " + r.out.trim());
        return "Installed glue " + rel.version + ". Restart to apply.";
    }

    private static byte[] get(String url) throws IOException {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setRequestProperty("User-Agent", "boox-einksettings");
        c.setRequestProperty("Accept", url.startsWith("https://api.github.com") ? "application/vnd.github+json" : "*/*");
        c.setConnectTimeout(15000);
        c.setReadTimeout(30000);
        c.setInstanceFollowRedirects(true);
        try {
            if (c.getResponseCode() != 200) throw new IOException("HTTP " + c.getResponseCode() + " for " + url);
            try (InputStream in = c.getInputStream()) { return readAll(in); }
        } finally {
            c.disconnect();
        }
    }

    private static byte[] readAll(InputStream in) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        byte[] buf = new byte[16384];
        int n;
        while ((n = in.read(buf)) > 0) {
            b.write(buf, 0, n);
            if (b.size() > 8 * 1024 * 1024) throw new IOException("download too large");
        }
        return b.toByteArray();
    }

    private static byte[] sha256(byte[] b) throws IOException {
        try {
            return MessageDigest.getInstance("SHA-256").digest(b);
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IOException(e);
        }
    }

    private static String hex(byte[] b) {
        StringBuilder s = new StringBuilder();
        for (byte x : b) s.append(String.format("%02x", x));
        return s.toString();
    }
}
