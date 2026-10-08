// fido2-net-lib (NuGet Fido2) driver: verify one fault-peer case as an integrator would and print the raw
// record. Same contract as webauthn/drivers/py_webauthn_driver.py. Usage: Fido2Driver <case-dir>
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using Fido2NetLib;
using Fido2NetLib.Objects;

var dir = args[0];
var opts = JsonNode.Parse(File.ReadAllText(Path.Combine(dir, "options.json")))!;
var body = File.ReadAllBytes(Path.Combine(dir, "response.json"));
static byte[] B64d(string s) => Convert.FromBase64String(s.Replace('-', '+').Replace('_', '/') + new string('=', (4 - s.Length % 4) % 4));
var fields = new JsonObject();
var rec = new JsonObject
{
    ["library"] = "fido2-net-lib",
    ["version"] = typeof(Fido2).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion?.Split('+')[0],
    ["passed_sha256"] = Convert.ToHexStringLower(SHA256.HashData(body)),
    ["returned_error"] = false,
    ["error_type"] = null,
    ["error"] = null,
};
string rpId = opts["rpId"]!.GetValue<string>();
var fido2 = new Fido2(new Fido2Configuration
{
    ServerDomain = rpId,
    ServerName = opts["rpName"]!.GetValue<string>(),
    Origins = new HashSet<string> { opts["origin"]!.GetValue<string>() },
});
var uv = opts["requireUserVerification"]!.GetValue<bool>() ? UserVerificationRequirement.Required : UserVerificationRequirement.Preferred;
var user = new Fido2User { Id = B64d(opts["userId"]!.GetValue<string>()), Name = opts["userName"]!.GetValue<string>(), DisplayName = opts["userName"]!.GetValue<string>() };
var challenge = B64d(opts["challenge"]!.GetValue<string>());
try
{
    if (opts["credential"] is null)
    {
        var create = fido2.RequestNewCredential(new RequestNewCredentialParams
        {
            User = user,
            ExcludeCredentials = [],
            AuthenticatorSelection = new AuthenticatorSelection { UserVerification = uv },
            AttestationPreference = opts["attestation"]!.GetValue<string>() == "none" ? AttestationConveyancePreference.None : AttestationConveyancePreference.Direct,
            PubKeyCredParams = [PubKeyCredParam.ES256],
        });
        create.Challenge = challenge;
        var resp = JsonSerializer.Deserialize<AuthenticatorAttestationRawResponse>(body)!;
        var res = await fido2.MakeNewCredentialAsync(new MakeNewCredentialParams
        {
            AttestationResponse = resp,
            OriginalOptions = create,
            IsCredentialIdUniqueToUserCallback = (_, _) => Task.FromResult(true),
        });
        fields["backup_eligible"] = res.IsBackupEligible;
        fields["backed_up"] = res.IsBackedUp;
        fields["attestation_type"] = res.AttestationType;
    }
    else
    {
        var c = opts["credential"]!;
        var credId = B64d(c["id"]!.GetValue<string>());
        var get = fido2.GetAssertionOptions(new GetAssertionOptionsParams
        {
            AllowedCredentials = [new PublicKeyCredentialDescriptor(credId)],
            UserVerification = uv,
        });
        get.Challenge = challenge;
        var resp = JsonSerializer.Deserialize<AuthenticatorAssertionRawResponse>(body)!;
        var res = await fido2.MakeAssertionAsync(new MakeAssertionParams
        {
            AssertionResponse = resp,
            OriginalOptions = get,
            StoredPublicKey = B64d(c["publicKeyCose"]!.GetValue<string>()),
            StoredSignatureCounter = c["signCount"]!.GetValue<uint>(),
            IsUserHandleOwnerOfCredentialIdCallback = (_, _) => Task.FromResult(true),
        });
        fields["sign_count"] = res.SignCount;
        fields["backed_up"] = res.IsBackedUp;
    }
}
catch (Exception e)
{
    rec["returned_error"] = true;
    rec["error_type"] = e.GetType().Name;
    var m = e.Message.Replace('\n', ' ');
    rec["error"] = m.Length > 300 ? m[..300] : m;
    fields.Clear();
}
rec["fields"] = fields;
Console.WriteLine(rec.ToJsonString());
