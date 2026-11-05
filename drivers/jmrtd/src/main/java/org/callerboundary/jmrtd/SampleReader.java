package org.callerboundary.jmrtd;

import org.jmrtd.BACKey;
import org.jmrtd.PassportService;
import org.jmrtd.lds.icao.DG15File;
import org.jmrtd.lds.icao.DG1File;
import org.jmrtd.lds.icao.MRZInfo;
import org.jmrtd.protocol.AAResult;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PublicKey;
import java.security.SecureRandom;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Consequence demo (T13): a small passport reader written the way public JMRTD integrations
 * use Active Authentication. It performs access control, reads DG1 and DG15, calls
 * {@code doAA} with the DG15 public key and a fresh challenge, and shows the document as
 * authentic unless the library throws. It does not inspect the returned AAResult: the library
 * is trusted to report a refused AA.
 *
 * <p>{@code -mode defensive} adds the one check the pre-registration fixes for the contrast run:
 * the returned response must be non-empty before the document is shown as authentic.
 *
 * <p>Usage: {@code java -cp jmrtd-driver.jar org.callerboundary.jmrtd.SampleReader
 * -profile P.json -chip-serve bin/chip-serve -mode pattern|defensive -out RESULT.json}
 */
public final class SampleReader {
    private SampleReader() {}

    public static void main(String[] args) throws Exception {
        Map<String, String> a = new LinkedHashMap<>();
        for (int i = 0; i + 1 < args.length; i += 2) {
            a.put(args[i], args[i + 1]);
        }
        String mode = a.getOrDefault("-mode", "pattern");
        if (!mode.equals("pattern") && !mode.equals("defensive")) {
            throw new IllegalArgumentException("-mode must be pattern or defensive");
        }
        HarnessProfile profile = HarnessProfile.load(Path.of(a.get("-profile")));
        BACKey bacKey = new BACKey(profile.mrz.documentNumber, profile.mrz.dateOfBirth, profile.mrz.dateOfExpiry);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("app", "SampleReader");
        result.put("mode", mode);
        result.put("profile", profile.id);
        boolean trustedChain = Boolean.parseBoolean(a.getOrDefault("-trusted-chain", "false"));
        result.put("trusted_chain", trustedChain);
        VpcdCardService card = VpcdCardService.harness(Path.of(a.get("-chip-serve")), a.get("-profile"), trustedChain);
        boolean authentic;
        String shown;
        try {
            PassportService service = JmrtdRead.openService(card);
            JmrtdRead.accessControl(service, JmrtdRead.readCardAccess(service), bacKey, new JmrtdRead.Step());
            MRZInfo mrz;
            try (InputStream in = service.getInputStream(PassportService.EF_DG1, PassportService.DEFAULT_MAX_BLOCKSIZE)) {
                mrz = new DG1File(in).getMRZInfo();
            }
            PublicKey aaKey;
            try (InputStream in = service.getInputStream(PassportService.EF_DG15, PassportService.DEFAULT_MAX_BLOCKSIZE)) {
                aaKey = new DG15File(in).getPublicKey();
            }
            byte[] challenge = new byte[8];
            new SecureRandom().nextBytes(challenge);
            AAResult aa = service.doAA(aaKey, "SHA-1", "SHA1WithRSA/ISO9796-2", challenge);
            byte[] response = aa == null ? null : aa.getResponse();
            result.put("aa_returned", true);
            result.put("aa_response_length", response == null ? 0 : response.length);
            authentic = mode.equals("pattern") || (response != null && response.length > 0);
            shown = mrz.getDocumentNumber() + " " + mrz.getPrimaryIdentifier() + " " + mrz.getSecondaryIdentifier().trim();
            result.put("error", null);
        } catch (Exception e) {
            result.put("aa_returned", false);
            result.put("error", e.getClass().getSimpleName() + ": " + JmrtdRead.describe(e));
            authentic = false;
            shown = null;
        } finally {
            card.close();
        }
        result.put("aa_refused_by_chip", card.faultDelivered("AA"));
        result.put("authentic", authentic);
        result.put("document_shown", shown);
        result.put("trace", JmrtdRead.trace(card.trace()));
        String line = String.format("[%s] %s  document=%s  authentic=%s", mode, profile.id, shown, authentic);
        System.out.println(line);
        result.put("display", line);
        if (a.containsKey("-out")) {
            Files.writeString(Path.of(a.get("-out")), new com.google.gson.GsonBuilder().setPrettyPrinting()
                    .serializeNulls().create().toJson(result) + "\n");
        }
    }
}
