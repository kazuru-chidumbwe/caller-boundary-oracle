#!/usr/bin/env python3
"""Write webauthn/heldout/expectations.json: the expected outcome of every (arm, case) pair of the held-out
evaluation, each with the source reason, derived from each release's source before the single run
(HELD-OUT-DESIGN.md). Sources read: the released artifacts (PyPI wheel, npm tarball, Go module zip, Maven
sources jar, GitHub tag archive) of each version in RELEASES.json.

Pairs run during development (pinned release x development case) are included with the outcome observed in
development and marked "development"; they are not part of the held-out claim.

Usage: python3 webauthn/heldout/write_expectations.py
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEV = HERE.parent / "dev" / "expectations-dev.json"

DEV_CASES = ["R-OK-NONE", "R-OK-PACKED", "R-TYPE", "R-CHAL", "R-ORIG", "R-RPID", "R-UP", "R-UV", "R-BS", "R-ASIG",
             "A-OK", "A-TYPE", "A-CHAL", "A-ORIG", "A-RPID", "A-UP", "A-UV", "A-BS", "A-SIG", "A-CNT"]
NEW_CASES = ["R-UPUV", "R-ORIGPORT", "R-XORIG", "R-NONESTMT", "R-ALG",
             "A-UPUV", "A-ORIGPORT", "A-XORIG", "A-UH", "A-CRED", "A-CNTEQ"]
CONTROLS = {"R-OK-NONE", "R-OK-PACKED", "A-OK"}
NA = ("not_applicable", "positive control: no fault injected; the ceremony must be accepted")

# ---------------------------------------------------------------------------------------------------------
# py_webauthn 3.0.1 and 2.8.0 (wheel sources). verify_authentication_response is byte-identical in the two;
# verify_registration_response differs only by an isinstance check on fmt (3.0.1 line 209); the other
# differing helpers add ML-DSA keys and reject duplicate CBOR keys, which no case uses.
PY_R = "webauthn/registration/verify_registration_response.py"
PY_A = "webauthn/authentication/verify_authentication_response.py"
PY = {
    "R-TYPE": ("surfaced", f"{PY_R}: client_data.type != webauthn.create raises (3.0.1 line 131)"),
    "R-CHAL": ("surfaced", f"{PY_R}: challenge mismatch raises (line 136)"),
    "R-ORIG": ("surfaced", f"{PY_R}: exact string comparison of origin raises (lines 139 to 143)"),
    "R-RPID": ("surfaced", f"{PY_R}: rp_id_hash mismatch raises (line 173)"),
    "R-UP": ("surfaced", f"{PY_R}: require_user_presence defaults to True; UP clear raises (line 176)"),
    "R-UV": ("surfaced", f"{PY_R}: require_user_verification=True from the driver; UV clear raises (line 181)"),
    "R-BS": ("surfaced", "webauthn/helpers/parse_backup_flags.py: BS without BE raises InvalidBackupFlags (lines 26 to 27), called at the end of verification"),
    "R-ASIG": ("surfaced", "webauthn/registration/formats/packed.py: without x5c (self attestation) the signature is verified with the credential key and InvalidSignature raises (lines 92 to 101)"),
    "R-UPUV": ("surfaced", f"{PY_R}: UP clear raises before the UV check (line 176); UV set does not matter"),
    "R-ORIGPORT": ("surfaced", f"{PY_R}: exact string comparison; 'https://rp.cbo.test:8443' != 'https://rp.cbo.test' raises (lines 139 to 143)"),
    "R-XORIG": ("silent", "webauthn/helpers/parse_client_data_json.py lines 40 to 42 parse crossOrigin into client_data.cross_origin; no verification step reads it and VerifiedRegistration does not return it"),
    "R-NONESTMT": ("surfaced", f"{PY_R}: fmt none with any attestation statement field set raises 'None attestation had unexpected attestation statement' (lines 220 to 229)"),
    "R-ALG": ("surfaced", f"{PY_R}: credential key alg -7 not in supported_pub_key_algs [-257] (passed by the driver) raises (line 204)"),
    "A-TYPE": ("surfaced", f"{PY_A}: type != webauthn.get raises (line 107)"),
    "A-CHAL": ("surfaced", f"{PY_A}: challenge mismatch raises (line 112)"),
    "A-ORIG": ("surfaced", f"{PY_A}: exact string comparison of origin raises (lines 115 to 119)"),
    "A-RPID": ("surfaced", f"{PY_A}: rp_id_hash mismatch raises (line 147)"),
    "A-UP": ("surfaced", f"{PY_A}: UP clear always raises (line 150)"),
    "A-UV": ("surfaced", f"{PY_A}: require_user_verification=True; UV clear raises (line 153)"),
    "A-BS": ("surfaced", "webauthn/helpers/parse_backup_flags.py: BS without BE raises (lines 26 to 27), called at line 187"),
    "A-SIG": ("surfaced", f"{PY_A}: InvalidSignature from verify_signature raises (lines 174 to 185)"),
    "A-CNT": ("surfaced", f"{PY_A}: a count not greater than the stored nonzero count raises (lines 158 to 166)"),
    "A-UPUV": ("surfaced", f"{PY_A}: UP clear always raises (line 150)"),
    "A-ORIGPORT": ("surfaced", f"{PY_A}: exact string comparison raises (lines 115 to 119)"),
    "A-XORIG": ("silent", "crossOrigin is parsed (parse_client_data_json.py lines 40 to 42) and never checked; VerifiedAuthentication does not return it"),
    "A-UH": ("silent", f"{PY_A}: the function takes no user or user handle (lines 47 to 56) and never reads response.user_handle; the caller must compare it"),
    "A-CRED": ("silent", f"{PY_A}: the function takes no allow list (lines 47 to 56); the caller passes the stored key for the presented ID and the signature verifies"),
    "A-CNTEQ": ("surfaced", f"{PY_A}: sign_count 10 <= stored 10 with a nonzero count raises (lines 158 to 166)"),
}

# ---------------------------------------------------------------------------------------------------------
# @simplewebauthn/server 14.0.3 and 13.3.3 (npm tarballs, esm build). Line numbers are 14.0.3. Registration
# differs only by the PQC guard and a renamed variable; authentication 14.0.3 adds the crossOrigin/topOrigin
# check (lines 74 to 111) and a PQC guard. A bad signature makes verifySignature return false, so the result
# is {verified: false} without an exception (status signal `verified`).
SW_R = "esm/registration/verifyRegistrationResponse.js"
SW_A = "esm/authentication/verifyAuthenticationResponse.js"
SW = {
    "R-TYPE": ("surfaced", f"{SW_R}: type != webauthn.create throws (line 64)"),
    "R-CHAL": ("surfaced", f"{SW_R}: challenge mismatch throws (line 73)"),
    "R-ORIG": ("surfaced", f"{SW_R}: origin !== expectedOrigin throws (line 83)"),
    "R-RPID": ("surfaced", f"{SW_R}: matchExpectedRPID throws on a hash that matches no expected RP ID (line 112)"),
    "R-UP": ("surfaced", f"{SW_R}: requireUserPresence defaults to true; UP clear throws (line 115)"),
    "R-UV": ("surfaced", f"{SW_R}: requireUserVerification true; UV clear throws (line 119)"),
    "R-BS": ("surfaced", "esm/helpers/parseBackupFlags.js: BS without BE throws InvalidBackupFlags (lines 12 to 16), called at line 202"),
    "R-ASIG": ("status_only", "esm/registration/verifications/verifyAttestationPacked.js: without x5c the self-attestation signature goes to verifySignature, which returns false; verifyRegistrationResponse returns {verified: false} (lines 199 to 200)"),
    "R-UPUV": ("surfaced", f"{SW_R}: UP clear throws (line 115) before the UV check"),
    "R-ORIGPORT": ("surfaced", f"{SW_R}: exact comparison origin !== expectedOrigin throws (line 83)"),
    "R-XORIG": ("silent", f"{SW_R}: destructures type, origin, challenge, tokenBinding only (line 51); crossOrigin and topOrigin are not read in registration, and the result is verified: true"),
    "R-NONESTMT": ("surfaced", f"{SW_R}: fmt none with attStmt.size > 0 throws (lines 189 to 192)"),
    "R-ALG": ("surfaced", f"{SW_R}: pubKeyAlg -7 not in supportedAlgorithmIDs [-257] (passed by the driver) throws (lines 137 to 140)"),
    "A-TYPE": ("surfaced", f"{SW_A}: type != webauthn.get throws (line 62)"),
    "A-CHAL": ("surfaced", f"{SW_A}: challenge mismatch throws (line 71)"),
    "A-ORIG": ("surfaced", f"{SW_A}: origin !== expectedOrigin throws (line 120)"),
    "A-RPID": ("surfaced", f"{SW_A}: matchExpectedRPID throws (line 153)"),
    "A-UP": ("surfaced", f"{SW_A}: without advancedFIDOConfig, UP clear throws (line 175)"),
    "A-UV": ("surfaced", f"{SW_A}: requireUserVerification true; UV clear throws (line 179)"),
    "A-BS": ("surfaced", "esm/helpers/parseBackupFlags.js: BS without BE throws (lines 12 to 16), called at line 202"),
    "A-SIG": ("status_only", f"{SW_A}: verified is the boolean returned by verifySignature (lines 203 to 208); a signature over other bytes gives verified: false without an exception"),
    "A-CNT": ("surfaced", f"{SW_A}: counter <= stored nonzero counter throws (lines 186 to 192)"),
    "A-UPUV": ("surfaced", f"{SW_A}: UP clear throws (line 175)"),
    "A-ORIGPORT": ("surfaced", f"{SW_A}: exact comparison throws (line 120)"),
    "A-UH": ("silent", f"{SW_A}: userHandle is only type-checked (lines 130 to 133) and never compared with a stored user; the result is verified: true"),
    "A-CRED": ("silent", f"{SW_A}: the options take one credential and no allow list (line 28); response.id is not compared with credential.id, and the signature verifies under the stored key"),
    "A-CNTEQ": ("surfaced", f"{SW_A}: counter 10 <= stored 10 with a nonzero counter throws (lines 186 to 192)"),
}
SW14 = dict(SW, **{"A-XORIG": ("surfaced", f"{SW_A}: crossOrigin true with topOrigin set and no expectedTopOrigin (the driver passes none) throws 'Detected cross-origin authentication response' (lines 75 to 88)")})
SW13 = dict(SW, **{"A-XORIG": ("silent", "13.3.3 esm/authentication/verifyAuthenticationResponse.js destructures type, origin, challenge, tokenBinding only (line 45); crossOrigin and topOrigin are never read and the result is verified: true")})

# ---------------------------------------------------------------------------------------------------------
# go-webauthn v0.18.2 and v0.17.4 (module zips from proxy.golang.org). Line numbers are v0.18.2 unless noted.
# Default Config: RPAllowCrossOrigin false; origins compared by scheme and host:port (client.go isOriginEqual,
# lines 333 to 343; a port other than 443 is kept in Host by parseOriginURI, lines 357 to 366).
GO_C = "protocol/client.go CollectedClientData.Verify"
GO = {
    "R-TYPE": ("surfaced", f"{GO_C}: type mismatch returns ErrVerification (line 146)"),
    "R-CHAL": ("surfaced", f"{GO_C}: challenge mismatch returns ErrVerification (line 158)"),
    "R-ORIG": ("surfaced", f"{GO_C}: origin not in RPOrigins returns ErrVerification (lines 167 to 179)"),
    "R-RPID": ("surfaced", "protocol/authenticator.go AuthenticatorData.Verify: RP hash mismatch returns ErrVerification (line 435)"),
    "R-UP": ("surfaced", "webauthn/registration.go: shouldVerifyUserPresence is true outside conditional mediation (line 204); AuthenticatorData.Verify returns an error when UP is clear (line 441)"),
    "R-UV": ("surfaced", "UserVerification required in the session; AuthenticatorData.Verify returns an error when UV is clear (line 448)"),
    "R-BS": ("surfaced", "webauthn/registration.go: BS without BE returns ErrBadRequest (lines 213 to 215)"),
    "R-ASIG": ("surfaced", "protocol/attestation_packed.go handleSelfAttestation: a signature that does not verify returns ErrInvalidAttestation"),
    "R-UPUV": ("surfaced", "AuthenticatorData.Verify: UP required and clear returns an error (line 441) before the UV check"),
    "R-ORIGPORT": ("surfaced", f"{GO_C}: 'rp.cbo.test:8443' and 'rp.cbo.test' differ in Host, so the origin is not in RPOrigins (lines 167 to 179, 333 to 343)"),
    "R-XORIG": ("surfaced", f"{GO_C}: crossOrigin true with RPAllowCrossOrigin false (default) returns 'Error validating cross origin flag' (lines 181 to 185)"),
    "R-NONESTMT": ("surfaced", "protocol/attestation.go VerifyAttestation: format none with a non-empty statement returns ErrAttestationFormat (lines 258 to 261)"),
    "R-ALG": ("surfaced", "protocol/attestation.go AttestationObject.Verify: key alg -7 not in session CredParams [-257] (from the driver) returns 'Credential public key algorithm not supported' (lines 226 to 234)"),
    "A-TYPE": ("surfaced", f"{GO_C}: type mismatch returns ErrVerification (line 146)"),
    "A-CHAL": ("surfaced", f"{GO_C}: challenge mismatch (line 158)"),
    "A-ORIG": ("surfaced", f"{GO_C}: origin not in RPOrigins (lines 167 to 179)"),
    "A-RPID": ("surfaced", "AuthenticatorData.Verify: RP hash mismatch (line 435)"),
    "A-UP": ("surfaced", "webauthn/login.go: shouldVerifyUserPresence := true (line 382); UP clear returns an error (authenticator.go line 441)"),
    "A-UV": ("surfaced", "UV required; UV clear returns an error (authenticator.go line 448)"),
    "A-BS": ("surfaced", "webauthn/login.go validateLogin: BS without BE returns ErrBadRequest (line 409)"),
    "A-SIG": ("surfaced", "protocol/assertion.go ParsedCredentialAssertionData.Verify: a signature that does not verify returns an error"),
    "A-CNT": ("status_only", "webauthn/authenticator.go UpdateCounter: a count not greater than the stored nonzero count sets CloneWarning and returns (lines 59 to 64); validateLogin returns the credential without error"),
    "A-UPUV": ("surfaced", "login.go line 382 requires UP; AuthenticatorData.Verify returns an error when UP is clear (line 441)"),
    "A-ORIGPORT": ("surfaced", f"{GO_C}: Host differs by port, origin not in RPOrigins (lines 167 to 179)"),
    "A-XORIG": ("surfaced", f"{GO_C}: crossOrigin true with RPAllowCrossOrigin false returns an error (lines 181 to 185)"),
    "A-UH": ("surfaced", "webauthn/login.go validateLogin: a present userHandle not equal to user.WebAuthnID() returns 'User handle and User ID do not match' (step 2)"),
    "A-CRED": ("surfaced", "webauthn/login.go validateLogin: with AllowedCredentialIDs set, an allow list the user does not own returns 'User does not own all credentials from the allowed credential list', and a credential ID outside the list returns ErrBadRequest (step 1)"),
    "A-CNTEQ": ("status_only", "webauthn/authenticator.go UpdateCounter: 10 <= stored 10 with a nonzero count sets CloneWarning and returns without error (lines 59 to 64)"),
}
GO17 = dict(GO, **{"R-BS": ("silent", "v0.17.4 webauthn/registration.go CreateCredential (lines 141 to 166) has no backup-flag check (added in the later line at v0.18.2 lines 213 to 215); the credential is returned and the driver reports BS and BE as raw flags only")})

# ---------------------------------------------------------------------------------------------------------
# java-webauthn-server 2.10.0 (webauthn-server-core sources jar), library defaults: allowOriginPort false,
# allowOriginSubdomain false, allowUntrustedAttestation true, validateSignatureCounter true. No class in the
# sources reads crossOrigin or topOrigin. 1.12.4 is not built (RELEASES.json), so only the new cases are held out.
YR = "com/yubico/webauthn/FinishRegistrationSteps.java"
YA = "com/yubico/webauthn/FinishAssertionSteps.java"
YUBICO_NEW = {
    "R-UPUV": ("surfaced", f"{YR}: Step14 asserts the UP flag unless the create is conditional (line 309); IllegalArgumentException"),
    "R-ORIGPORT": ("surfaced", f"{YR}: Step9 OriginMatcher.isAllowed (line 220) accepts only an exact match when allowOriginPort and allowOriginSubdomain are false (OriginMatcher.java)"),
    "R-XORIG": ("silent", "no source file of webauthn-server-core 2.10.0 reads crossOrigin or topOrigin; finishRegistration succeeds and RegistrationResult has no cross-origin field"),
    "R-NONESTMT": ("silent", f"{YR}: Step18 maps fmt none to NoneAttestationStatementVerifier (line 418), whose verifyAttestationSignature returns true without reading the statement; allowUntrustedAttestation defaults to true, so registration succeeds"),
    "R-ALG": ("surfaced", f"{YR}: Step16 asserts that the key alg is in pubKeyCredParams (line 362); the request lists RS256 only"),
    "A-UPUV": ("surfaced", f"{YA}: Step16 asserts the UP flag (line 486)"),
    "A-ORIGPORT": ("surfaced", f"{YA}: Step13 OriginMatcher.isAllowed (line 418), exact match only under the defaults"),
    "A-XORIG": ("silent", "crossOrigin is not read anywhere in 2.10.0; finishAssertion succeeds with isSuccess true"),
    "A-UH": ("surfaced", f"{YA}: Step6 asserts that the request user handle equals the response user handle (line 271)"),
    "A-CRED": ("surfaced", f"{YA}: Step5 asserts that the response credential ID is in allowCredentials ('Unrequested credential ID', line 173)"),
    "A-CNTEQ": ("surfaced", f"{YA}: Step21 throws InvalidSignatureCountException when validateSignatureCounter is true and the count is not greater than the stored nonzero count (lines 641 and 646 to 648)"),
}

# ---------------------------------------------------------------------------------------------------------
# webauthn4j-core 0.31.11.RELEASE and 0.30.3.RELEASE (Maven sources jars), both arms. The driver builds
# ServerProperty(origin, rpId, challenge, null), so no top-origin predicate is set; RegistrationParameters and
# AuthenticationParameters get userPresenceRequired true and UV required. The non-strict factory replaces only the
# attestation statement and trustworthiness verifiers with Null verifiers (WebAuthnManager lines 180 to 194 in
# both releases); every other check is shared. Line numbers: 0.31.11 (0.30.3 in parentheses).
WR = "com/webauthn4j/verifier/RegistrationDataVerifier.java"
WA = "com/webauthn4j/verifier/AuthenticationDataVerifier.java"
W4J_NEW = {
    "R-UPUV": ("surfaced", f"{WR}: UPUVFlagsVerifier.verify with userPresenceRequired throws UserNotPresentException (line 209 (188))"),
    "R-ORIGPORT": ("surfaced", f"{WR}: OriginVerifierImpl throws BadOriginException; SimpleOriginPredicate uses Origin.equals, which compares scheme, host and port (443 against 8443) (line 171 (158))"),
    "R-XORIG": ("surfaced", f"{WR}: TopOriginVerifier throws BadTopOriginException when crossOrigin is true and no top-origin predicate is configured (line 187 (171); verifier/internal/TopOriginVerifier.java)"),
    "R-NONESTMT": ("surfaced", f"{WR}: BeanAssertUtil.validate (line 125 (112)) calls NoneAttestationStatement.validate, which throws BadAttestationStatementException when any property was set (data/attestation/statement/NoneAttestationStatement.java line 32); this runs before the statement verifiers, so in both arms"),
    "R-ALG": ("surfaced", f"{WR}: COSEAlgorithmIdentifierVerifier.verify(alg, pubKeyCredParams) throws for ES256 against [RS256] (line 231 (207))"),
    "A-UPUV": ("surfaced", f"{WA}: UPUVFlagsVerifier.verify throws UserNotPresentException (line 204 (182))"),
    "A-ORIGPORT": ("surfaced", f"{WA}: OriginVerifierImpl throws BadOriginException (line 174 (156))"),
    "A-XORIG": ("surfaced", f"{WA}: TopOriginVerifier throws BadTopOriginException (line 183 (163))"),
    "A-UH": ("silent", f"{WA}: step 6 (user handle) is marked 'out of WebAuthn4J scope. It's caller's responsibility' (lines 120 to 128 (96 to 103)); AuthenticationParameters carries no user handle and verification succeeds"),
    "A-CRED": ("surfaced", f"{WA}: CredentialIdVerifier.verify throws NotAllowedCredentialIdException for an ID not in allowCredentials (line 117 (92))"),
    "A-CNTEQ": ("surfaced", f"{WA}: presentedSignCount 10 is not greater than stored 10, so DefaultCoreMaliciousCounterValueHandler throws MaliciousCounterValueException (lines 228 to 247 (217 to 234))"),
}
W4J_DEV = {
    "R-TYPE": ("surfaced", f"{WR}: InconsistentClientDataTypeException when type is not webauthn.create"),
    "R-CHAL": ("surfaced", f"{WR}: ChallengeVerifier throws BadChallengeException"),
    "R-ORIG": ("surfaced", f"{WR}: OriginVerifierImpl throws BadOriginException (line (158))"),
    "R-RPID": ("surfaced", f"{WR}: RpIdHashVerifier throws BadRpIdException"),
    "R-UP": ("surfaced", f"{WR}: UPUVFlagsVerifier throws UserNotPresentException (line (188))"),
    "R-UV": ("surfaced", f"{WR}: UPUVFlagsVerifier throws UserNotVerifiedException (line (188))"),
    "R-BS": ("surfaced", f"{WR}: BEBSFlagsVerifier throws IllegalBackupStateException (line (192))"),
    "A-TYPE": ("surfaced", f"{WA}: InconsistentClientDataTypeException when type is not webauthn.get"),
    "A-CHAL": ("surfaced", f"{WA}: ChallengeVerifier throws BadChallengeException"),
    "A-ORIG": ("surfaced", f"{WA}: OriginVerifierImpl throws BadOriginException (line (156))"),
    "A-RPID": ("surfaced", f"{WA}: RpIdHashVerifier throws BadRpIdException"),
    "A-UP": ("surfaced", f"{WA}: UPUVFlagsVerifier throws UserNotPresentException (line (182))"),
    "A-UV": ("surfaced", f"{WA}: UPUVFlagsVerifier throws UserNotVerifiedException (line (182))"),
    "A-BS": ("surfaced", f"{WA}: BEBSFlagsVerifier throws IllegalBackupStateException (line (186))"),
    "A-SIG": ("surfaced", "com/webauthn4j/verifier/internal/AssertionSignatureVerifier throws BadSignatureException; shared by both arms"),
    "A-CNT": ("surfaced", f"{WA}: count 5 below stored 10 goes to DefaultCoreMaliciousCounterValueHandler, which throws MaliciousCounterValueException (lines (217 to 234))"),
}
W4J_STRICT_30 = dict(W4J_DEV, **W4J_NEW, **{"R-ASIG": ("surfaced", "strict arm: PackedAttestationStatementVerifier verifies the self-attestation signature with the credential key and throws BadSignatureException")})
W4J_NONSTRICT_30 = dict(W4J_DEV, **W4J_NEW, **{"R-ASIG": ("silent", "non-strict arm: createNonStrictWebAuthnManager uses NullPackedAttestationStatementVerifier and NullSelfAttestationTrustworthinessVerifier (WebAuthnManager lines 180 to 194), so the packed signature is not verified and registration succeeds")})

# ---------------------------------------------------------------------------------------------------------
# Fido2 (fido2-net-lib) 4.2.0 and 5.0.0-preview.7 (GitHub tag archives, Src/Fido2). Default Fido2Configuration:
# AllowCrossOriginRequests false (5.0 only; 4.2.0 has no crossOrigin member), backup policies Allowed. Origins are
# compared after ToFullyQualifiedOrigin, which keeps a non-default port (Fido2.Models/StringExtensions.cs).
# The driver's IsUserHandleOwnerOfCredentialIdCallback compares handle and credential ID with the stored ones.
# Line numbers: 4.2.0 / 5.0.0-preview.7.
FR = "Src/Fido2/AuthenticatorAttestationResponse.cs"
FA = "Src/Fido2/AuthenticatorAssertionResponse.cs"
FB = "Src/Fido2/AuthenticatorResponse.cs BaseVerify"
FIDO_NEW_COMMON = {
    "R-UPUV": ("surfaced", f"{FR}: UP clear throws UserPresentFlagNotSet (139 / 147, the latter outside conditional mediation)"),
    "R-ORIGPORT": ("surfaced", f"{FB}: 'https://rp.cbo.test:8443' is not in the fully qualified expected origins (103 / 125)"),
    "R-NONESTMT": ("surfaced", "Src/Fido2/AttestationFormat/None.cs: AttStmt.Count != 0 throws 'Attestation format none should have no attestation statement' (line 12, both)"),
    "R-ALG": ("surfaced", f"{FR}: no PubKeyCredParams entry ([RS256] from the driver) matches the key alg; throws CredentialAlgorithmRequirementNotMet (161 / 175)"),
    "A-UPUV": ("surfaced", f"{FA}: UP clear throws UserPresentFlagNotSet outside conformance testing (164 / 181)"),
    "A-ORIGPORT": ("surfaced", f"{FB}: origin with port 8443 not in the expected origins (103 / 125)"),
    "A-UH": ("surfaced", f"{FA}: the driver's IsUserHandleOwnerOfCredentialId callback returns false for another user's handle, and the library throws UserHandleNotOwnerOfPublicKey (124 to 126 / 141 to 143)"),
    "A-CRED": ("surfaced", f"{FA}: AllowCredentials not containing the raw ID throws CredentialIdNotInAllowedCredentials (111 to 115 / 118 to 122)"),
    "A-CNTEQ": ("surfaced", f"{FA}: (SignCount != 0 or stored != 0) and SignCount <= stored throws InvalidSignCount (211 / 247)"),
}
FIDO42_NEW = dict(FIDO_NEW_COMMON, **{
    "R-XORIG": ("silent", "4.2.0 AuthenticatorResponse has no crossOrigin or topOrigin member (Src/Fido2/AuthenticatorResponse.cs lines 55 to 68), so the flag is never read; registration succeeds and the result has no cross-origin field"),
    "A-XORIG": ("silent", "4.2.0 never reads crossOrigin (no member in AuthenticatorResponse); MakeAssertionAsync succeeds"),
})
FIDO50 = dict(FIDO_NEW_COMMON, **{
    "R-XORIG": ("surfaced", f"{FB}: crossOrigin true with AllowCrossOriginRequests false (default) throws CrossOriginRequestNotAllowed (5.0.0-preview.7 lines 135 to 136)"),
    "A-XORIG": ("surfaced", f"{FB}: crossOrigin true with AllowCrossOriginRequests false throws CrossOriginRequestNotAllowed"),
    "R-TYPE": ("surfaced", f"{FR}: type other than webauthn.create throws (line 93)"),
    "R-CHAL": ("surfaced", f"{FB}: challenge mismatch throws InvalidAuthenticatorResponseChallenge"),
    "R-ORIG": ("surfaced", f"{FB}: origin not in the expected origins throws (line 125)"),
    "R-RPID": ("surfaced", f"{FR}: RP ID hash mismatch throws InvalidRpidHash (line 142)"),
    "R-UP": ("surfaced", f"{FR}: UP clear throws UserPresentFlagNotSet (line 147)"),
    "R-UV": ("surfaced", f"{FR}: UV required and clear throws UserVerificationRequirementNotMet (line 151)"),
    "R-BS": ("surfaced", f"{FR}: BS without BE throws InvalidBackupFlags (lines 157 to 158), the Level 3 check absent from 4.2.0"),
    "R-ASIG": ("surfaced", "Src/Fido2/AttestationFormat/Packed.cs: self attestation verifies the signature with the credential key and throws when it fails (line 165)"),
    "A-TYPE": ("surfaced", f"{FA}: type other than webauthn.get throws (line 157)"),
    "A-CHAL": ("surfaced", f"{FB}: challenge mismatch throws"),
    "A-ORIG": ("surfaced", f"{FB}: origin not in the expected origins throws (line 125)"),
    "A-RPID": ("surfaced", f"{FA}: RP ID hash mismatch throws InvalidRpidHash (line 175)"),
    "A-UP": ("surfaced", f"{FA}: UP clear throws (line 181)"),
    "A-UV": ("surfaced", f"{FA}: UV required and clear throws (line 186)"),
    "A-BS": ("surfaced", f"{FA}: BS without BE throws InvalidBackupFlags (lines 191 to 192)"),
    "A-SIG": ("surfaced", f"{FA}: a signature that does not verify throws InvalidSignature (line 241)"),
    "A-CNT": ("surfaced", f"{FA}: count 5 not greater than stored 10 throws InvalidSignCount (lines 247 to 248)"),
})

# Fido2 4.3.2 (NuGet, 29 Oct 2026): the 4.x line with PR #690, which backports the Level 3 crossOrigin/topOrigin
# and BS-without-BE checks after our report #689 (U3, added 5 Nov 2026 before the run). Source: GitHub tag 4.3.2
# (f7ed63c), Src/Fido2. Line numbers are 4.3.2.
FIDO43 = dict(FIDO_NEW_COMMON, **{
    "R-UPUV": ("surfaced", f"{FR}: UP clear throws UserPresentFlagNotSet (line 140)"),
    "R-ORIGPORT": ("surfaced", f"{FB}: 'https://rp.cbo.test:8443' is not in the fully qualified expected origins (line 124)"),
    "R-NONESTMT": ("surfaced", "Src/Fido2/AttestationFormat/None.cs: AttStmt.Count != 0 throws (line 13)"),
    "R-ALG": ("surfaced", f"{FR}: no PubKeyCredParams entry matches the key alg; throws CredentialAlgorithmRequirementNotMet (line 168)"),
    "A-UPUV": ("surfaced", f"{FA}: UP clear throws UserPresentFlagNotSet outside conformance testing (line 165)"),
    "A-ORIGPORT": ("surfaced", f"{FB}: origin with port 8443 not in the expected origins (line 124)"),
    "A-UH": ("surfaced", f"{FA}: callback returns false for another user's handle; throws UserHandleNotOwnerOfPublicKey (line 126)"),
    "A-CRED": ("surfaced", f"{FA}: AllowCredentials not containing the raw ID throws CredentialIdNotInAllowedCredentials (line 115)"),
    "A-CNTEQ": ("surfaced", f"{FA}: (SignCount != 0 or stored != 0) and SignCount <= stored throws InvalidSignCount (line 220)"),
    "R-XORIG": ("surfaced", f"{FB}: crossOrigin true with AllowCrossOriginRequests false (default) throws CrossOriginRequestNotAllowed (lines 133 to 134), backported by #690"),
    "A-XORIG": ("surfaced", f"{FB}: crossOrigin true with AllowCrossOriginRequests false throws CrossOriginRequestNotAllowed (lines 133 to 134)"),
    "R-TYPE": ("surfaced", f"{FB}: type other than webauthn.create or webauthn.get throws (line 93); {FR} rejects webauthn.get (line 91)"),
    "R-CHAL": ("surfaced", f"{FB}: challenge mismatch throws InvalidAuthenticatorResponseChallenge (line 105)"),
    "R-ORIG": ("surfaced", f"{FB}: origin not in the expected origins throws (line 124)"),
    "R-RPID": ("surfaced", f"{FR}: RP ID hash mismatch throws InvalidRpidHash (line 136)"),
    "R-UP": ("surfaced", f"{FR}: UP clear throws UserPresentFlagNotSet (line 140)"),
    "R-UV": ("surfaced", f"{FR}: UV required and clear throws UserVerificationRequirementNotMet (line 144)"),
    "R-BS": ("surfaced", f"{FR}: BS without BE throws InvalidBackupFlags (lines 149 to 150), backported by #690"),
    "R-ASIG": ("surfaced", "Src/Fido2/AttestationFormat/Packed.cs: self attestation verifies the signature with the credential key and throws 'Failed to validate signature' (line 151)"),
    "A-TYPE": ("surfaced", f"{FA}: type other than webauthn.get throws (line 140)"),
    "A-CHAL": ("surfaced", f"{FB}: challenge mismatch throws (line 105)"),
    "A-ORIG": ("surfaced", f"{FB}: origin not in the expected origins throws (line 124)"),
    "A-RPID": ("surfaced", f"{FA}: RP ID hash mismatch throws InvalidRpidHash (line 158)"),
    "A-UP": ("surfaced", f"{FA}: UP clear throws (line 165)"),
    "A-UV": ("surfaced", f"{FA}: UV required and clear throws (line 169)"),
    "A-BS": ("surfaced", f"{FA}: BS without BE throws InvalidBackupFlags (lines 174 to 175), backported by #690"),
    "A-SIG": ("surfaced", f"{FA}: a signature that does not verify throws InvalidSignature (line 213)"),
    "A-CNT": ("surfaced", f"{FA}: count 5 not greater than stored 10 throws InvalidSignCount (line 220)"),
})


# L1 current-release recheck (added 16 Nov 2026 before the run). Each newer release is predicted from its source
# diff against the release already measured: if no verification step that a case reaches changed, the case keeps
# that release's outcome and reason. Diffs read on GitHub (compare views) on 16 Nov 2026.
DERIVED: dict[str, tuple[str, str]] = {
    "simplewebauthn@14.1.0": ("simplewebauthn",
        "same as 14.0.3: v14.0.3...v14.1.0 moves the origin check into helpers/matchExpectedOrigin.ts (exact match, "
        "plus BAD_ARGUMENT for an expected origin with a trailing slash or non-ASCII characters, which ours has not), "
        "adds ASCII checks of the expected RP ID, and adds a provider-metadata lookup after verification that returns "
        "nothing while MetadataService and ConvenienceMetadataService are DISABLED (not initialised by the driver); "
        "the other changes are TPM and Android Key attestation, which no case uses"),
    "java-webauthn-server@2.10.1": ("java-webauthn-server",
        "same as 2.10.0: 2.10.0...2.10.1 changes only webauthn-server-attestation MetadataStatement.java "
        "(userVerificationDetails optional, MDS 3.1) and CI; webauthn-server-core is unchanged"),
    "webauthn4j-nonstrict@0.32.0.RELEASE": ("webauthn4j-nonstrict",
        "same as 0.31.11: 0.31.11...0.32.0 adds ML-DSA keys and algorithms, iOS App Attest changes, and makes "
        "AuthenticatorDataConverter parse attested credential data whenever the AT flag is set (registration cases "
        "carry it; assertion cases have no AT flag); no verifier step a case reaches changed"),
    "webauthn4j-strict@0.32.0.RELEASE": ("webauthn4j-strict",
        "same as 0.31.11: 0.31.11...0.32.0 adds ML-DSA keys and algorithms, iOS App Attest changes, and makes "
        "AuthenticatorDataConverter parse attested credential data whenever the AT flag is set (registration cases "
        "carry it; assertion cases have no AT flag); no verifier step a case reaches changed"),
    "fido2-net-lib@4.3.3": ("fido2-net-lib@4.3.2",
        "same as 4.3.2: 4.3.2...4.3.3 is one commit, System.Formats.Cbor 9.0.0 to 9.0.24 in Directory.Packages.props "
        "(GHSA-vmv3-wvjp-wqpj); no Src/Fido2 change"),
    "fido2-net-lib@5.0.0-preview.10": ("fido2-net-lib@5.0.0-preview.7",
        "same as 5.0.0-preview.7: preview.7...preview.10 adds Secure Payment Confirmation (payment.get accepted only "
        "when a payment is expected; assertion step 10 still requires webauthn.get otherwise), AAGUID allow and deny "
        "lists (empty by default), metadata-consistency checks (off without a metadata statement), and the SafetyNet "
        "x5c[0] signer fix; none applies to a case under the driver's default configuration"),
}

ARMS: dict[str, dict[str, tuple[str, str]]] = {
    "py_webauthn": PY,
    "py_webauthn@2.8.0": PY,
    "simplewebauthn": SW14,
    "simplewebauthn@13.3.3": SW13,
    "go-webauthn": GO,
    "go-webauthn@v0.17.4": GO17,
    "java-webauthn-server": YUBICO_NEW,
    "webauthn4j-nonstrict": W4J_NEW,
    "webauthn4j-strict": W4J_NEW,
    "webauthn4j-nonstrict@0.30.3.RELEASE": W4J_NONSTRICT_30,
    "webauthn4j-strict@0.30.3.RELEASE": W4J_STRICT_30,
    "fido2-net-lib": FIDO42_NEW,
    "fido2-net-lib@5.0.0-preview.7": FIDO50,
    "fido2-net-lib@4.3.2": FIDO43,
}


def main() -> None:
    dev = json.loads(DEV.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for arm, table in ARMS.items():
        pinned = "@" not in arm
        rows = {}
        for case in DEV_CASES + NEW_CASES:
            if pinned and case in DEV_CASES:
                e = dev[arm][case]
                rows[case] = {"outcome": e["outcome"], "reason": "development: " + e["reason"], "held_out": False}
                continue
            outcome, reason = NA if case in CONTROLS else table[case]
            rows[case] = {"outcome": outcome, "reason": reason, "held_out": True}
        out[arm] = rows
    for arm, (base, note) in DERIVED.items():
        out[arm] = {case: {"outcome": r["outcome"], "reason": f"{note}. Base: {r['reason']}", "held_out": True}
                    for case, r in out[base].items()}
    (HERE / "expectations.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    n = sum(1 for a in out.values() for r in a.values() if r["held_out"])
    print(f"{len(out)} arms, {n} held-out pairs")


if __name__ == "__main__":
    main()
