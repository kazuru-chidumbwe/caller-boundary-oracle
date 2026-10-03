package org.callerboundary.jmrtd;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

/** The shared oracle vectors (Go and Python read the same file). */
public class ObservabilityTest {

    @Test
    void sharedVectors() throws Exception {
        Path vectors = Path.of("../../testdata/observability-vectors.json");
        JsonArray rows = JsonParser.parseString(Files.readString(vectors)).getAsJsonArray();
        assertFalse(rows.isEmpty());
        for (JsonElement el : rows) {
            JsonObject row = el.getAsJsonObject();
            JsonObject in = row.getAsJsonObject("input");
            Observability.Outcome got = Observability.classify(new Observability.Observation(
                    in.get("fired").getAsBoolean(),
                    in.get("failed").getAsBoolean(),
                    in.get("succeeded").getAsBoolean(),
                    in.get("returned_error").getAsBoolean(),
                    in.get("status_signal").getAsBoolean()));
            String id = row.get("id").getAsString();
            assertEquals(row.get("outcome").getAsString(), got.value, id);
            Integer want = row.get("score").isJsonNull() ? null : row.get("score").getAsInt();
            assertEquals(want, got.score, id);
        }
    }

    @Test
    void notFiredIsNotSurfaced() {
        assertEquals(Observability.Outcome.NOT_APPLICABLE,
                Observability.classify(new Observability.Observation(false, true, false, true, false)));
    }
}
