package org.callerboundary.jmrtd050;

import org.jmrtd.BACKey;
import org.jmrtd.MRTDTrustStore;
import org.jmrtd.Passport;
import org.jmrtd.PassportService;
import org.jmrtd.VerificationStatus;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * One oracle observation against JMRTD 0.5.0, through the entry point an application of that
 * release used: {@code new Passport(service, trustStore, bacKey)}, which opens the document, tries
 * PACE when EF.CardAccess offers it, falls back to BAC on its own, and reads the document.
 *
 * <p>The library's own record of the PACE step is {@code getVerificationStatus().getSAC()}:
 * FAILED counts as failed (and is readable by the caller, so also a status signal), SUCCEEDED as
 * succeeded. An exception from the constructor is the returned error. Only PACE is driven: the
 * 0.5.0 history point is about how a PACE failure reaches the caller.
 */
public final class Jmrtd050Read {
    public static void main(String[] args) throws Exception {
        RunnerArgs a = RunnerArgs.parse(args);
        Path root = Path.of(".").toAbsolutePath().normalize();
        HarnessProfile profile = HarnessProfile.load(a.profilePath);
        String mechanism = profile.mechanism == null ? "" : profile.mechanism.toUpperCase();
        if (!mechanism.equals("PACE")) {
            throw new IllegalArgumentException("the JMRTD 0.5.0 driver covers PACE only, not " + profile.mechanism);
        }
        boolean vsc = "vsmartcard".equals(profile.peer);
        VpcdCardService card = vsc
                ? VpcdCardService.independent(root, a.profilePath.toString())
                : VpcdCardService.harness(a.chipServe, a.profilePath.toString());
        String readErr = "";
        String exceptionClass = "";
        VerificationStatus.Verdict sac = null;
        VerificationStatus.Verdict bac = null;
        try {
            PassportService service = new PassportService(card);
            BACKey key = new BACKey(profile.mrz.documentNumber, profile.mrz.dateOfBirth, profile.mrz.dateOfExpiry);
            Passport passport = new Passport(service, new MRTDTrustStore(), key);
            sac = passport.getVerificationStatus().getSAC();
            bac = passport.getVerificationStatus().getBAC();
        } catch (Exception e) {
            readErr = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
            exceptionClass = e.getClass().getName();
        } finally {
            card.close();
        }
        boolean fired = card.faultDelivered("PACE");
        boolean failed = sac == VerificationStatus.Verdict.FAILED;
        boolean succeeded = sac == VerificationStatus.Verdict.SUCCEEDED;
        Observability.Observation observation = new Observability.Observation(
                fired, failed, succeeded, !readErr.isEmpty(), failed);
        Observability.Outcome outcome = Observability.classify(observation);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("run_id", RunIds.next(profile.id + "-jmrtd-" + a.variant));
        result.put("test_case", profile.id);
        result.put("library", "jmrtd");
        result.put("mechanism", mechanism);
        result.put("condition", profile.condition);
        result.put("tier", profile.tier != null ? profile.tier : "wire");
        result.put("variant", a.variant);
        result.put("provenance", Provenance.collect(root, a.profilePath, a.suiteId, a.suiteSeed, a.suiteN, a.runIndex,
                "java/Jmrtd050Read", a.variant, "entry=Passport"));
        result.put("outcome", outcome.value);
        result.put("observability_score", outcome.score);
        result.put("observability_meaning", outcome.meaning);
        result.put("fault_point", JmrtdFaultPoint.of(profile, vsc));
        Map<String, Object> obs = new LinkedHashMap<>();
        obs.put("fired", observation.fired());
        obs.put("failed", observation.failed());
        obs.put("succeeded", observation.succeeded());
        obs.put("returned_error", observation.returnedError());
        obs.put("status_signal", observation.statusSignal());
        result.put("observation", obs);
        result.put("sac_verdict", sac == null ? null : sac.name());
        result.put("bac_verdict", bac == null ? null : bac.name());
        result.put("read_err", readErr);
        result.put("exception", exceptionClass);
        List<Map<String, Object>> trace = new ArrayList<>();
        for (VpcdCardService.TraceEntry e : card.trace()) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("label", e.label);
            row.put("capdu", e.capdu);
            row.put("rapdu", e.rapdu);
            row.put("success", e.success);
            trace.add(row);
        }
        result.put("trace", trace);
        Provenance.writeResult(a.logDir, (String) result.get("run_id"), result);
        System.out.printf("%s %s jmrtd 0.5.0: %s%n", profile.id, a.variant, outcome.value);
    }

    /** Fault point names, as in the 0.8.9 driver. */
    static final class JmrtdFaultPoint {
        static String of(HarnessProfile profile, boolean vsc) {
            if (vsc) {
                String step = profile.vsmartcard == null ? null : profile.vsmartcard.paceStep;
                if (step == null || step.isEmpty()) {
                    return "";
                }
                return step.equals("mse") ? "PACE/mse_set_at" : "PACE/general_authenticate_step" + step.substring(2);
            }
            if (profile.cardAccessHex == null || profile.cardAccessHex.isEmpty()
                    || profile.injection == null || profile.injection.paceFailOn == null) {
                return "";
            }
            return "PACE/" + profile.injection.paceFailOn;
        }
    }
}
