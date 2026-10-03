namespace CallerBoundary.EmrtdDotnet;

/// <summary>What a driver records for one run. Fired comes from the chip; the rest from the library and caller code.</summary>
public sealed record Observation(bool Fired, bool Failed, bool Succeeded, bool ReturnedError, bool StatusSignal);

/// <summary>Caller-boundary oracle: the same predicate as classifier/observability.go, .py and Observability.java.</summary>
public static class Oracle
{
    public static string Classify(Observation o)
    {
        if (o.Failed && o.Succeeded) return "invalid";
        if (!o.Fired) return "not_applicable";
        if (o.ReturnedError) return "surfaced";
        if (o.StatusSignal) return "status_only";
        return "silent";
    }

    public static int? Score(string outcome) => outcome switch
    {
        "silent" => 0,
        "status_only" => 1,
        "surfaced" => 2,
        _ => null,
    };

    public static string Meaning(string outcome) => outcome switch
    {
        "silent" => "silent: call succeeded, failure not reachable by the caller",
        "status_only" => "status-only: call succeeded, failure recorded in a returned status field",
        "surfaced" => "surfaced: error returned or thrown to the caller",
        "not_applicable" => "not applicable: injected failure did not fire",
        _ => "invalid: library reported the step as both failed and successful",
    };
}
