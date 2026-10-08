package org.callerboundary.jmrtd050;

/**
 * Caller-boundary oracle: the same predicate as classifier/observability.go and
 * classifier/observability.py, checked against testdata/observability-vectors.json.
 */
public final class Observability {
    private Observability() {}

    /**
     * What a driver records for one run. {@code fired} comes from the simulated card (the
     * injected failure was delivered); the other fields from the library and the read routine.
     */
    public record Observation(boolean fired, boolean failed, boolean succeeded, boolean returnedError, boolean statusSignal) {}

    public enum Outcome {
        SILENT("silent", 0, "silent: call succeeded, failure not reachable by the caller"),
        STATUS_ONLY("status_only", 1, "status-only: call succeeded, failure recorded in a returned status field"),
        SURFACED("surfaced", 2, "surfaced: error returned or thrown to the caller"),
        NOT_APPLICABLE("not_applicable", null, "not applicable: injected failure did not fire"),
        INVALID("invalid", null, "invalid: library reported the step as both failed and successful");

        public final String value;
        public final Integer score;
        public final String meaning;

        Outcome(String value, Integer score, String meaning) {
            this.value = value;
            this.score = score;
            this.meaning = meaning;
        }
    }

    /** Invalid and not-applicable are decided before any score is assigned. */
    public static Outcome classify(Observation o) {
        if (o.failed() && o.succeeded()) {
            return Outcome.INVALID;
        }
        if (!o.fired()) {
            return Outcome.NOT_APPLICABLE;
        }
        if (o.returnedError()) {
            return Outcome.SURFACED;
        }
        if (o.statusSignal()) {
            return Outcome.STATUS_ONLY;
        }
        return Outcome.SILENT;
    }
}
