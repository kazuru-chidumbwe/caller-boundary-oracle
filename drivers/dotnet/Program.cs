// One oracle observation against emrtd-dotnet: start a chip (harness chip-serve or the
// independent vsmartcard chip), call DocumentReader.Read as an application would, and record
// the caller-boundary outcome for PACE. emrtd-dotnet implements PACE and BAC but not CA or AA.
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using CallerBoundary.EmrtdDotnet;
using Emrtd;

var a = Args.Parse(args);
if (a.CheckVectors is not null) return CheckVectors(a.CheckVectors);

string root = Directory.GetCurrentDirectory();
var profile = JsonNode.Parse(File.ReadAllText(a.Profile))!.AsObject();
string id = (string)profile["id"]!;
string mechanism = ((string?)profile["mechanism"] ?? "").ToUpperInvariant();
if (mechanism != "PACE") throw new ArgumentException($"emrtd-dotnet implements PACE and BAC only; profile mechanism is {mechanism}");
var mrz = profile["mrz"]!.AsObject();
var key = new MrzKey((string)mrz["document_number"]!, (string)mrz["date_of_birth"]!, (string)mrz["date_of_expiry"]!);
bool vsc = (string?)profile["peer"] == "vsmartcard";
string report = Path.Combine(Path.GetTempPath(), $"chip-report-{Guid.NewGuid():N}.json");

var log = new List<string>();
string readErr = "";
string? accessControl = null;
VpcdTransport transport = vsc
    ? new VpcdTransport("python3", port => [Path.Combine(root, "tools/vsmartcard/emrtd_card.py"), "--port", port.ToString(),
        "--profile", a.Profile, "--report", report])
    : new VpcdTransport(a.ChipServe, port => ["-profile", a.Profile, "-port", port.ToString(), "-report", report]);
try
{
    var doc = new DocumentReader(transport, log.Add).Read(key, new ReadOptions { UsePace = true, ReadFace = false });
    accessControl = doc.AccessControl;
}
catch (Exception ex)
{
    readErr = $"{ex.GetType().Name}: {ex.Message}";
}
finally
{
    transport.Dispose();
}

bool fired = false;
if (File.Exists(report))
{
    fired = JsonNode.Parse(File.ReadAllText(report))!["fault_delivered"]?["PACE"]?.GetValue<bool>() ?? false;
    File.Delete(report);
}
// emrtd-dotnet reports a PACE failure only in its log callback; the returned document names the
// access control actually used, which is how a caller can tell that PACE did not complete.
bool failed = log.Any(l => l.StartsWith("PACE failed", StringComparison.Ordinal));
bool succeeded = accessControl?.StartsWith("PACE", StringComparison.Ordinal) ?? false;
var observation = new Observation(
    Fired: fired,
    Failed: failed,
    Succeeded: succeeded,
    ReturnedError: readErr.Length > 0,
    StatusSignal: accessControl is not null && !succeeded);
string outcome = Oracle.Classify(observation);

string runId = $"{id}-emrtd-dotnet-{a.Variant}-{DateTime.UtcNow:yyyyMMdd'T'HHmmss.ffffff'Z'}-{a.RunIndex:D6}";
var result = new JsonObject
{
    ["run_id"] = runId,
    ["test_case"] = id,
    ["library"] = "emrtd-dotnet",
    ["mechanism"] = mechanism,
    ["condition"] = (string?)profile["condition"],
    ["tier"] = (string?)profile["tier"] ?? "wire",
    ["variant"] = a.Variant,
    ["provenance"] = Provenance(root, a),
    ["outcome"] = outcome,
    ["observability_score"] = Oracle.Score(outcome),
    ["observability_meaning"] = Oracle.Meaning(outcome),
    ["observation"] = new JsonObject
    {
        ["fired"] = observation.Fired,
        ["failed"] = observation.Failed,
        ["succeeded"] = observation.Succeeded,
        ["returned_error"] = observation.ReturnedError,
        ["status_signal"] = observation.StatusSignal,
    },
    ["fault_point"] = FaultPoint(profile, vsc),
    ["access_control"] = accessControl,
    ["read_err"] = readErr,
    ["library_log"] = new JsonArray(log.Select(l => (JsonNode)JsonValue.Create(l)!).ToArray()),
    ["trace"] = new JsonArray(transport.Trace.Select(t => (JsonNode)new JsonObject
    {
        ["label"] = t.Label, ["capdu"] = t.Capdu, ["rapdu"] = t.Rapdu, ["success"] = t.Success,
    }).ToArray()),
};
Directory.CreateDirectory(a.LogDir);
File.WriteAllText(Path.Combine(a.LogDir, runId + ".json"),
    result.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + "\n");
Console.WriteLine($"{id} {a.Variant} emrtd-dotnet: {outcome}");
return 0;

static string FaultPoint(JsonObject profile, bool vsc)
{
    if (vsc)
    {
        // "mse" is PACE/mse_set_at, "gaN" is PACE/general_authenticate_stepN (internal/profile).
        string step = (string?)profile["vsmartcard"]?["pace_step"] ?? "";
        return step switch
        {
            "" => "",
            "mse" => "PACE/mse_set_at",
            _ when step.Length == 3 && step.StartsWith("ga") => "PACE/general_authenticate_step" + step[2..],
            _ => "PACE/" + step,
        };
    }
    string? cardAccess = (string?)profile["card_access_hex"];
    string? failOn = (string?)profile["injection"]?["pace_fail_on"];
    return string.IsNullOrEmpty(cardAccess) || string.IsNullOrEmpty(failOn) ? "" : "PACE/" + failOn;
}

static JsonObject Provenance(string root, Args a)
{
    string profileFull = Path.GetFullPath(a.Profile);
    string rel = Path.GetRelativePath(root, profileFull).Replace('\\', '/');
    return new JsonObject
    {
        ["harness_commit"] = Git(root, "rev-parse", "HEAD") ?? "unknown",
        ["harness_dirty"] = (Git(root, "status", "--porcelain", "--untracked-files=no") ?? "").Length > 0,
        ["emrtd_dotnet_commit"] = Git(Environment.GetEnvironmentVariable("EmrtdDotnetDir") is { Length: > 0 } dir ? dir : Path.Combine(root, "../_vendor/emrtd-dotnet"), "rev-parse", "HEAD"),
        ["dotnet_version"] = Environment.Version.ToString(),
        ["profile_path"] = rel,
        ["profile_sha256"] = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(profileFull))).ToLowerInvariant(),
        ["suite_id"] = a.SuiteId,
        ["suite_seed"] = a.SuiteSeed,
        ["suite_n"] = a.SuiteN,
        ["run_index"] = a.RunIndex,
        ["driver"] = "dotnet/EmrtdDotnetRead",
        ["variant"] = a.Variant,
        ["caller_options"] = null,
        ["captured_at_utc"] = CapturedAt(),
    };
}

static string CapturedAt()
{
    string? epoch = Environment.GetEnvironmentVariable("SOURCE_DATE_EPOCH");
    return long.TryParse(epoch, out long s)
        ? DateTimeOffset.FromUnixTimeSeconds(s).UtcDateTime.ToString("yyyy-MM-ddTHH:mm:ssZ")
        : DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ");
}

static string? Git(string dir, params string[] gitArgs)
{
    try
    {
        var psi = new ProcessStartInfo("git") { RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false };
        psi.ArgumentList.Add("-C");
        psi.ArgumentList.Add(dir);
        foreach (string g in gitArgs) psi.ArgumentList.Add(g);
        using var p = Process.Start(psi)!;
        string output = p.StandardOutput.ReadToEnd().Trim();
        p.WaitForExit();
        return p.ExitCode == 0 ? output : null;
    }
    catch (Exception)
    {
        return null;
    }
}

static int CheckVectors(string path)
{
    int failures = 0;
    foreach (var row in JsonNode.Parse(File.ReadAllText(path))!.AsArray())
    {
        var i = row!["input"]!;
        var o = new Observation(i["fired"]!.GetValue<bool>(), i["failed"]!.GetValue<bool>(), i["succeeded"]!.GetValue<bool>(),
            i["returned_error"]!.GetValue<bool>(), i["status_signal"]!.GetValue<bool>());
        string got = Oracle.Classify(o);
        int? want = row["score"] is null ? null : row["score"]!.GetValue<int>();
        if (got != (string)row["outcome"]! || Oracle.Score(got) != want)
        {
            Console.Error.WriteLine($"vector {(string)row["id"]!}: got {got}");
            failures++;
        }
    }
    Console.WriteLine(failures == 0 ? "vectors OK" : $"{failures} vector(s) failed");
    return failures == 0 ? 0 : 1;
}

sealed class Args
{
    public string Profile = "";
    public string LogDir = "logs";
    public string Variant = "default";
    public string SuiteId = "";
    public int SuiteSeed = 1;
    public int SuiteN = 1;
    public int RunIndex = 1;
    public string ChipServe = "bin/chip-serve";
    public string? CheckVectors;

    public static Args Parse(string[] argv)
    {
        var a = new Args();
        for (int i = 0; i < argv.Length; i++)
        {
            switch (argv[i])
            {
                case "-profile": a.Profile = argv[++i]; break;
                case "-log-dir": a.LogDir = argv[++i]; break;
                case "-variant": a.Variant = argv[++i]; break;
                case "-suite-id": a.SuiteId = argv[++i]; break;
                case "-suite-seed": a.SuiteSeed = int.Parse(argv[++i]); break;
                case "-suite-n": a.SuiteN = int.Parse(argv[++i]); break;
                case "-run-index": a.RunIndex = int.Parse(argv[++i]); break;
                case "-chip-serve": a.ChipServe = argv[++i]; break;
                case "-check-vectors": a.CheckVectors = argv[++i]; break;
                default: throw new ArgumentException($"unknown argument {argv[i]}");
            }
        }
        return a;
    }
}
