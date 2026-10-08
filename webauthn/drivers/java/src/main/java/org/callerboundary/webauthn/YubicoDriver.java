package org.callerboundary.webauthn;

import com.yubico.webauthn.AssertionRequest;
import com.yubico.webauthn.AssertionResult;
import com.yubico.webauthn.CredentialRepository;
import com.yubico.webauthn.FinishAssertionOptions;
import com.yubico.webauthn.FinishRegistrationOptions;
import com.yubico.webauthn.RegisteredCredential;
import com.yubico.webauthn.RegistrationResult;
import com.yubico.webauthn.RelyingParty;
import com.yubico.webauthn.data.AttestationConveyancePreference;
import com.yubico.webauthn.data.AuthenticatorSelectionCriteria;
import com.yubico.webauthn.data.ByteArray;
import com.yubico.webauthn.data.PublicKeyCredential;
import com.yubico.webauthn.data.PublicKeyCredentialCreationOptions;
import com.yubico.webauthn.data.PublicKeyCredentialDescriptor;
import com.yubico.webauthn.data.PublicKeyCredentialParameters;
import com.yubico.webauthn.data.PublicKeyCredentialRequestOptions;
import com.yubico.webauthn.data.RelyingPartyIdentity;
import com.yubico.webauthn.data.UserIdentity;
import com.yubico.webauthn.data.UserVerificationRequirement;
import java.nio.file.Path;
import java.util.List;
import java.util.Optional;
import java.util.Set;

/**
 * java-webauthn-server (com.yubico:webauthn-server-core) driver. The relying party is built with
 * the library's defaults; only the identity, origin and credential repository are set, as in the
 * library's README. Usage: java -cp ... org.callerboundary.webauthn.YubicoDriver <case-dir>
 */
public final class YubicoDriver {
    public static void main(String[] args) throws Exception {
        Record r = new Record("java-webauthn-server", RelyingParty.class.getPackage().getImplementationVersion(), Path.of(args[0]));
        RelyingPartyIdentity rpId = RelyingPartyIdentity.builder().id(r.opt("rpId")).name(r.opt("rpName")).build();
        ByteArray userHandle = new ByteArray(Record.b64d(r.opt("userId")));
        String userName = r.opt("userName");
        Optional<RegisteredCredential> stored = Optional.empty();
        if (!r.registration()) {
            var c = r.options.get("credential");
            stored = Optional.of(RegisteredCredential.builder()
                    .credentialId(new ByteArray(Record.b64d(c.get("id").asText())))
                    .userHandle(userHandle)
                    .publicKeyCose(new ByteArray(Record.b64d(c.get("publicKeyCose").asText())))
                    .signatureCount(c.get("signCount").asLong())
                    .build());
        }
        final Optional<RegisteredCredential> cred = stored;
        CredentialRepository repo = new CredentialRepository() {
            public Set<PublicKeyCredentialDescriptor> getCredentialIdsForUsername(String u) {
                return cred.map(c -> Set.of(PublicKeyCredentialDescriptor.builder().id(c.getCredentialId()).build())).orElse(Set.of());
            }
            public Optional<ByteArray> getUserHandleForUsername(String u) {
                return Optional.of(userHandle);
            }
            public Optional<String> getUsernameForUserHandle(ByteArray h) {
                return Optional.of(userName);
            }
            public Optional<RegisteredCredential> lookup(ByteArray id, ByteArray h) {
                return cred.filter(c -> c.getCredentialId().equals(id));
            }
            public Set<RegisteredCredential> lookupAll(ByteArray id) {
                return cred.filter(c -> c.getCredentialId().equals(id)).map(Set::of).orElse(Set.of());
            }
        };
        RelyingParty rp = RelyingParty.builder().identity(rpId).credentialRepository(repo).origins(Set.of(r.opt("origin"))).build();
        ByteArray challenge = new ByteArray(Record.b64d(r.opt("challenge")));
        UserVerificationRequirement uv = r.options.get("requireUserVerification").asBoolean()
                ? UserVerificationRequirement.REQUIRED : UserVerificationRequirement.PREFERRED;
        try {
            if (r.registration()) {
                PublicKeyCredentialCreationOptions req = PublicKeyCredentialCreationOptions.builder()
                        .rp(rpId)
                        .user(UserIdentity.builder().name(userName).displayName(userName).id(userHandle).build())
                        .challenge(challenge)
                        .pubKeyCredParams(List.of(PublicKeyCredentialParameters.ES256))
                        .authenticatorSelection(AuthenticatorSelectionCriteria.builder().userVerification(uv).build())
                        .attestation("none".equals(r.opt("attestation")) ? AttestationConveyancePreference.NONE : AttestationConveyancePreference.DIRECT)
                        .build();
                RegistrationResult res = rp.finishRegistration(FinishRegistrationOptions.builder()
                        .request(req).response(PublicKeyCredential.parseRegistrationResponseJson(new String(r.body))).build());
                r.fields.put("user_verified", res.isUserVerified());
                r.fields.put("backup_eligible", res.isBackupEligible());
                r.fields.put("backed_up", res.isBackedUp());
                r.fields.put("attestation_trusted", res.isAttestationTrusted());
                r.fields.put("attestation_type", String.valueOf(res.getAttestationType()));
            } else {
                AssertionRequest req = AssertionRequest.builder()
                        .publicKeyCredentialRequestOptions(PublicKeyCredentialRequestOptions.builder()
                                .challenge(challenge).rpId(r.opt("rpId")).userVerification(uv).build())
                        .userHandle(userHandle)
                        .build();
                AssertionResult res = rp.finishAssertion(FinishAssertionOptions.builder()
                        .request(req).response(PublicKeyCredential.parseAssertionResponseJson(new String(r.body))).build());
                r.fields.put("success", res.isSuccess());
                r.fields.put("signature_counter_valid", res.isSignatureCounterValid());
                r.fields.put("user_verified", res.isUserVerified());
                r.fields.put("backed_up", res.isBackedUp());
                r.fields.put("signature_count", res.getSignatureCount());
            }
        } catch (Exception e) {
            r.error(e);
        }
        r.print();
    }
}
