package org.callerboundary.webauthn;

import com.webauthn4j.WebAuthnManager;
import com.webauthn4j.anchor.TrustAnchorRepository;
import com.webauthn4j.converter.util.ObjectConverter;
import com.webauthn4j.credential.CredentialRecord;
import com.webauthn4j.credential.CredentialRecordImpl;
import com.webauthn4j.data.AuthenticationData;
import com.webauthn4j.data.AuthenticationParameters;
import com.webauthn4j.data.PublicKeyCredentialParameters;
import com.webauthn4j.data.PublicKeyCredentialType;
import com.webauthn4j.data.RegistrationData;
import com.webauthn4j.data.RegistrationParameters;
import com.webauthn4j.data.attestation.authenticator.AAGUID;
import com.webauthn4j.data.attestation.authenticator.AttestedCredentialData;
import com.webauthn4j.data.attestation.authenticator.COSEKey;
import com.webauthn4j.data.attestation.statement.COSEAlgorithmIdentifier;
import com.webauthn4j.data.attestation.statement.NoneAttestationStatement;
import com.webauthn4j.data.client.Origin;
import com.webauthn4j.data.client.challenge.DefaultChallenge;
import com.webauthn4j.server.ServerProperty;
import com.webauthn4j.verifier.attestation.statement.none.NoneAttestationStatementVerifier;
import com.webauthn4j.verifier.attestation.statement.packed.PackedAttestationStatementVerifier;
import com.webauthn4j.verifier.attestation.trustworthiness.certpath.DefaultCertPathTrustworthinessVerifier;
import com.webauthn4j.verifier.attestation.trustworthiness.self.DefaultSelfAttestationTrustworthinessVerifier;
import java.nio.file.Path;
import java.util.List;
import java.util.Set;

/**
 * webauthn4j driver, two arms (the integrator's choice of manager):
 *   nonstrict  WebAuthnManager.createNonStrictWebAuthnManager(), the factory the library offers for
 *              relying parties that do not verify attestation
 *   strict     a manager with the packed and none statement verifiers, self attestation allowed and
 *              an empty trust-anchor repository
 * Usage: java -cp ... org.callerboundary.webauthn.Webauthn4jDriver nonstrict|strict <case-dir>
 */
public final class Webauthn4jDriver {
    /** The algorithms the relying party listed in options.json (ES256 when absent). */
    static List<PublicKeyCredentialParameters> algs(Record r) {
        var n = r.options.get("pubKeyCredParams");
        var out = new java.util.ArrayList<PublicKeyCredentialParameters>();
        if (n == null || n.isEmpty()) {
            out.add(new PublicKeyCredentialParameters(PublicKeyCredentialType.PUBLIC_KEY, COSEAlgorithmIdentifier.ES256));
        } else {
            for (var a : n) out.add(new PublicKeyCredentialParameters(PublicKeyCredentialType.PUBLIC_KEY, COSEAlgorithmIdentifier.create(a.asLong())));
        }
        return out;
    }

    /** The credential IDs the relying party allowed in options.json (the stored one when absent). */
    static List<byte[]> allow(Record r) {
        var n = r.options.get("allowCredentials");
        var out = new java.util.ArrayList<byte[]>();
        if (n == null || n.isEmpty()) {
            out.add(Record.b64d(r.options.get("credential").get("id").asText()));
        } else {
            for (var s : n) out.add(Record.b64d(s.asText()));
        }
        return out;
    }

    public static void main(String[] args) throws Exception {
        String arm = args[0];
        // the jar carries no version metadata; the file name copied by Maven does
        String jar = Path.of(WebAuthnManager.class.getProtectionDomain().getCodeSource().getLocation().toURI()).getFileName().toString();
        Record r = new Record("webauthn4j-" + arm, jar.replaceAll("^webauthn4j-core-(.*)\\.jar$", "$1"), Path.of(args[1]));
        WebAuthnManager m = switch (arm) {
            case "nonstrict" -> WebAuthnManager.createNonStrictWebAuthnManager();
            case "strict" -> {
                TrustAnchorRepository anchors = new TrustAnchorRepository() {
                    public Set<java.security.cert.TrustAnchor> find(AAGUID aaguid) { return Set.of(); }
                    public Set<java.security.cert.TrustAnchor> find(byte[] keyId) { return Set.of(); }
                };
                yield new WebAuthnManager(List.of(new PackedAttestationStatementVerifier(), new NoneAttestationStatementVerifier()),
                        new DefaultCertPathTrustworthinessVerifier(anchors), new DefaultSelfAttestationTrustworthinessVerifier(true));
            }
            default -> throw new IllegalArgumentException(arm);
        };
        ServerProperty server = new ServerProperty(new Origin(r.opt("origin")), r.opt("rpId"),
                new DefaultChallenge(Record.b64d(r.opt("challenge"))), null);
        boolean uv = r.options.get("requireUserVerification").asBoolean();
        try {
            if (r.registration()) {
                RegistrationData d = m.parseRegistrationResponseJSON(new String(r.body));
                m.verify(d, new RegistrationParameters(server,
                        algs(r), uv, true));
                var ad = d.getAttestationObject().getAuthenticatorData();
                r.fields.put("user_verified", ad.isFlagUV());
                r.fields.put("backup_eligible", ad.isFlagBE());
                r.fields.put("backup_state", ad.isFlagBS());
                r.fields.put("attestation_format", d.getAttestationObject().getFormat());
            } else {
                var c = r.options.get("credential");
                COSEKey key = new ObjectConverter().getCborConverter().readValue(Record.b64d(c.get("publicKeyCose").asText()), COSEKey.class);
                CredentialRecord rec = new CredentialRecordImpl(new NoneAttestationStatement(), true, false, false,
                        c.get("signCount").asLong(), new AttestedCredentialData(AAGUID.ZERO, Record.b64d(c.get("id").asText()), key),
                        null, null, null, null);
                AuthenticationData d = m.parseAuthenticationResponseJSON(new String(r.body));
                m.verify(d, new AuthenticationParameters(server, rec, allow(r), uv, true));
                var ad = d.getAuthenticatorData();
                r.fields.put("user_verified", ad.isFlagUV());
                r.fields.put("backup_state", ad.isFlagBS());
                r.fields.put("sign_count", ad.getSignCount());
            }
        } catch (Exception e) {
            r.error(e);
        }
        r.print();
    }
}
