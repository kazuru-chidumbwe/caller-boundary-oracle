package org.callerboundary.webauthn;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Map;

/** The raw record every WebAuthn driver prints; same contract as webauthn/drivers/py_webauthn_driver.py. */
final class Record {
    static final ObjectMapper JSON = new ObjectMapper();

    final JsonNode options;
    final byte[] body;
    final Map<String, Object> out = new LinkedHashMap<>();
    final Map<String, Object> fields = new LinkedHashMap<>();

    Record(String library, String version, Path dir) throws Exception {
        options = JSON.readTree(Files.readAllBytes(dir.resolve("options.json")));
        body = Files.readAllBytes(dir.resolve("response.json"));
        out.put("library", library);
        out.put("version", version);
        out.put("passed_sha256", HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(body)));
        out.put("returned_error", false);
        out.put("error_type", null);
        out.put("error", null);
        out.put("fields", fields);
    }

    boolean registration() {
        return !options.has("credential");
    }

    String opt(String k) {
        return options.get(k).asText();
    }

    static byte[] b64d(String s) {
        return Base64.getUrlDecoder().decode(s);
    }

    void error(Throwable e) {
        out.put("returned_error", true);
        out.put("error_type", e.getClass().getSimpleName());
        String m = String.valueOf(e.getMessage()).replace('\n', ' ');
        out.put("error", m.length() > 300 ? m.substring(0, 300) : m);
        fields.clear();
    }

    void print() throws Exception {
        System.out.println(JSON.writeValueAsString(out));
    }
}
