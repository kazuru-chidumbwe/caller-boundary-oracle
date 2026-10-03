package org.callerboundary.jmrtd;

import net.sf.scuba.smartcards.CardService;
import net.sf.scuba.util.Hex;
import org.jmrtd.BACKey;
import org.jmrtd.PassportService;
import org.jmrtd.lds.CardAccessFile;
import org.jmrtd.lds.PACEInfo;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.file.Path;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.AlgorithmParameterSpec;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * One oracle observation against JMRTD. JMRTD exposes protocol steps (doPACE, doBAC, doAA)
 * and reports a failed step by throwing; whether that reaches the application is decided by
 * the read routine the integrator writes. The driver therefore runs a named integrator pattern:
 *
 * <ul>
 *   <li>{@code propagate}: the step exception leaves the read routine.</li>
 *   <li>{@code catch-continue}: the read routine catches the step exception, logs it and
 *       continues (BAC after a failed PACE, reading on after a failed AA). This is the
 *       pattern found in public JMRTD integrations.</li>
 * </ul>
 *
 * Neither pattern returns a status object, so a caught failure is silent at the boundary
 * of the read routine.
 */
public final class JmrtdRead {
    enum Integrator { PROPAGATE, CATCH_CONTINUE }

    /** Thrown by the read routine when the integrator pattern lets a step failure through. */
    static final class ReadFailure extends Exception {
        ReadFailure(String step, Exception cause) {
            super(step + ": " + describe(cause), cause);
        }
    }

    /** Outcome of the targeted protocol step. */
    static final class Step {
        boolean failed;
        boolean succeeded;
        boolean bacSuccess;
        String err = "";
        String exceptionClass = "";

        void fail(Exception e) {
            failed = true;
            err = describe(e);
            exceptionClass = e.getClass().getName();
        }
    }

    public static void main(String[] args) throws Exception {
        RunnerArgs a = RunnerArgs.parse(args);
        Integrator integrator = switch (a.integrator) {
            case "propagate" -> Integrator.PROPAGATE;
            case "catch-continue" -> Integrator.CATCH_CONTINUE;
            default -> throw new IllegalArgumentException("-integrator must be propagate or catch-continue");
        };
        Path root = Path.of(".").toAbsolutePath().normalize();
        HarnessProfile profile = HarnessProfile.load(a.profilePath);
        String mechanism = profile.mechanism == null ? "" : profile.mechanism.toUpperCase();
        BACKey bacKey = new BACKey(profile.mrz.documentNumber, profile.mrz.dateOfBirth, profile.mrz.dateOfExpiry);

        Step step = new Step();
        List<Map<String, Object>> trace;
        String readErr = "";
        boolean fired;
        boolean vsc = "vsmartcard".equals(profile.peer);
        switch (mechanism) {
            case "PACE" -> {
                if (vsc) {
                    VsmartcardCardService card = new VsmartcardCardService(root, a.profilePath.toString());
                    try {
                        PassportService service = openService(card);
                        readWithPace(service, readCardAccess(service), bacKey, integrator, step, true);
                    } catch (ReadFailure e) {
                        readErr = e.getMessage();
                    } finally {
                        card.close();
                    }
                    fired = card.faultDelivered("PACE");
                    trace = trace(card.trace());
                } else {
                    String paceSw = profile.injection != null && profile.injection.paceSw != null ? profile.injection.paceSw : "6FFF";
                    String failOn = profile.injection != null && profile.injection.paceFailOn != null ? profile.injection.paceFailOn : "mse_set_at";
                    String channel = profile.injection != null && profile.injection.paceChannel != null ? profile.injection.paceChannel : "sw";
                    PaceFailureCardService card = new PaceFailureCardService(bacKey, paceSw, failOn, channel);
                    try {
                        readWithPace(openService(card), profileCardAccess(profile), bacKey, integrator, step, false);
                    } catch (ReadFailure e) {
                        readErr = e.getMessage();
                    }
                    fired = card.faultDelivered();
                    trace = trace(card.trace());
                }
            }
            case "AA" -> {
                if (vsc) {
                    VsmartcardCardService card = new VsmartcardCardService(root, a.profilePath.toString());
                    try {
                        PassportService service = openService(card);
                        readWithAa(service, readCardAccess(service), bacKey, integrator, step);
                    } catch (ReadFailure e) {
                        readErr = e.getMessage();
                    } finally {
                        card.close();
                    }
                    fired = card.faultDelivered("AA");
                    trace = trace(card.trace());
                } else {
                    String aaSw = profile.aaInjection != null && profile.aaInjection.aaSw != null ? profile.aaInjection.aaSw : "6982";
                    AaFailureCardService card = new AaFailureCardService(bacKey, aaSw);
                    try {
                        readWithAa(openService(card), null, bacKey, integrator, step);
                    } catch (ReadFailure e) {
                        readErr = e.getMessage();
                    }
                    fired = card.faultDelivered();
                    trace = trace(card.trace());
                }
            }
            default -> throw new IllegalArgumentException("unsupported mechanism " + profile.mechanism);
        }

        Observability.Observation observation = new Observability.Observation(
                fired, step.failed, step.succeeded, !readErr.isEmpty(), false);
        Observability.Outcome outcome = Observability.classify(observation);

        String integratorName = integrator == Integrator.PROPAGATE ? "propagate" : "catch-continue";
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("run_id", RunIds.next(profile.id + "-jmrtd-" + a.variant));
        result.put("test_case", profile.id);
        result.put("library", "jmrtd");
        result.put("mechanism", mechanism);
        result.put("condition", profile.condition);
        result.put("tier", profile.tier != null ? profile.tier : "wire");
        result.put("variant", a.variant);
        result.put("figure_id", a.figureId.isEmpty() ? null : a.figureId);
        result.put("provenance", Provenance.collect(root, a.profilePath, a.suiteId, a.suiteSeed, a.suiteN, a.runIndex,
                "java/JmrtdRead", a.variant, "integrator=" + integratorName));
        result.put("outcome", outcome.value);
        result.put("observability_score", outcome.score);
        result.put("observability_meaning", outcome.meaning);
        result.put("integrator", integratorName);
        result.put("fault_point", faultPoint(profile, mechanism));
        Map<String, Object> obs = new LinkedHashMap<>();
        obs.put("fired", observation.fired());
        obs.put("failed", observation.failed());
        obs.put("succeeded", observation.succeeded());
        obs.put("returned_error", observation.returnedError());
        obs.put("status_signal", observation.statusSignal());
        result.put("observation", obs);
        result.put("step_exception", step.exceptionClass);
        result.put("step_err", step.err);
        result.put("read_err", readErr);
        result.put("bac_success", step.bacSuccess);
        result.put("trace", trace);
        Provenance.writeResult(a.logDir, (String) result.get("run_id"), result);
        System.out.printf("%s %s jmrtd (%s): %s%n", profile.id, a.variant, integratorName, outcome.value);
    }

    static PassportService openService(CardService card) throws Exception {
        PassportService service = PassportServices.open(card);
        service.open();
        return service;
    }

    /** EF.CardAccess as served by the chip (null when the chip has none). */
    static byte[] readCardAccess(PassportService service) {
        try (InputStream in = service.getInputStream(PassportService.EF_CARD_ACCESS, PassportService.DEFAULT_MAX_BLOCKSIZE)) {
            return in.readAllBytes();
        } catch (Exception e) {
            return null;
        }
    }

    static byte[] profileCardAccess(HarnessProfile profile) {
        return profile.cardAccessHex == null || profile.cardAccessHex.isEmpty() ? null : Hex.hexStringToBytes(profile.cardAccessHex);
    }

    /**
     * A read routine: PACE when CardAccess advertises it, BAC if PACE did not complete, then
     * (when readCom is set) EF.COM over the established secure channel.
     */
    static void readWithPace(PassportService service, byte[] cardAccessBytes, BACKey bacKey, Integrator integrator,
            Step step, boolean readCom) throws Exception {
        boolean paceDone = false;
        if (cardAccessBytes != null) {
            CardAccessFile cardAccess = new CardAccessFile(new ByteArrayInputStream(cardAccessBytes));
            PACEInfo paceInfo = PassportServices.firstPaceInfo(cardAccess);
            try {
                AlgorithmParameterSpec params = PACEInfo.toParameterSpec(paceInfo.getParameterId());
                service.doPACE(bacKey, paceInfo.getObjectIdentifier(), params, paceInfo.getParameterId());
                step.succeeded = true;
                paceDone = true;
            } catch (Exception e) {
                step.fail(e);
                if (integrator == Integrator.PROPAGATE) {
                    throw new ReadFailure("PACE", e);
                }
            }
        }
        service.sendSelectApplet(paceDone);
        if (!paceDone) {
            try {
                service.doBAC(bacKey);
                step.bacSuccess = true;
            } catch (Exception e) {
                throw new ReadFailure("BAC", e);
            }
        }
        if (readCom) {
            try (InputStream in = service.getInputStream(PassportService.EF_COM, PassportService.DEFAULT_MAX_BLOCKSIZE)) {
                in.readAllBytes();
            } catch (Exception e) {
                throw new ReadFailure("EF.COM", e);
            }
        }
    }

    /**
     * A read routine: access control (PACE when CardAccess advertises it, otherwise BAC), then
     * Active Authentication. Only the AA step is the target; access-control failures propagate.
     */
    static void readWithAa(PassportService service, byte[] cardAccessBytes, BACKey bacKey, Integrator integrator, Step step)
            throws Exception {
        try {
            if (cardAccessBytes != null) {
                PACEInfo paceInfo = PassportServices.firstPaceInfo(new CardAccessFile(new ByteArrayInputStream(cardAccessBytes)));
                service.doPACE(bacKey, paceInfo.getObjectIdentifier(),
                        PACEInfo.toParameterSpec(paceInfo.getParameterId()), paceInfo.getParameterId());
                service.sendSelectApplet(true);
            } else {
                service.doBAC(bacKey);
            }
            step.bacSuccess = true;
        } catch (Exception e) {
            throw new ReadFailure("access control", e);
        }
        KeyPairGenerator kpg = KeyPairGenerator.getInstance("RSA");
        kpg.initialize(2048);
        RSAPublicKey pub = (RSAPublicKey) kpg.generateKeyPair().getPublic();
        try {
            service.doAA(pub, "SHA-256", "SHA256withRSA", new byte[] {1, 2, 3, 4, 5, 6, 7, 8});
            step.succeeded = true;
        } catch (Exception e) {
            step.fail(e);
            if (integrator == Integrator.PROPAGATE) {
                throw new ReadFailure("AA", e);
            }
        }
    }

    static String describe(Exception e) {
        return e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
    }

    static List<Map<String, Object>> trace(List<PaceFailureCardService.TraceEntry> entries) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (PaceFailureCardService.TraceEntry e : entries) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("label", e.label);
            row.put("capdu", e.capdu);
            row.put("rapdu", e.rapdu);
            row.put("success", e.success);
            out.add(row);
        }
        return out;
    }

    /** The step the profile injects the failure into ("" when nothing is injected). */
    static String faultPoint(HarnessProfile profile, String mechanism) {
        boolean vsc = "vsmartcard".equals(profile.peer);
        return switch (mechanism) {
            case "PACE" -> vsc
                    ? vscPaceFaultPoint(profile.vsmartcard == null ? null : profile.vsmartcard.paceStep)
                    : profile.cardAccessHex == null || profile.cardAccessHex.isEmpty()
                        || profile.injection == null || profile.injection.paceFailOn == null
                        ? "" : "PACE/" + profile.injection.paceFailOn;
            case "AA" -> vsc
                    ? (profile.vsmartcard == null || profile.vsmartcard.aaSw == null || profile.vsmartcard.aaSw.isEmpty()
                        ? "" : "AA/internal_authenticate")
                    : (profile.aaInjection == null ? "" : "AA/" + profile.aaInjection.aaFailOn);
            default -> "";
        };
    }

    /** "mse" is PACE/mse_set_at, "gaN" is PACE/general_authenticate_stepN (internal/profile). */
    static String vscPaceFaultPoint(String step) {
        if (step == null || step.isEmpty()) {
            return "";
        }
        if (step.equals("mse")) {
            return "PACE/mse_set_at";
        }
        if (step.length() == 3 && step.startsWith("ga")) {
            return "PACE/general_authenticate_step" + step.substring(2);
        }
        return "PACE/" + step;
    }
}
