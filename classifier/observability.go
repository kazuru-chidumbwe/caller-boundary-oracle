// Package classifier implements the caller-boundary oracle.
//
// The oracle is domain-neutral: a driver injects a failure into one negotiation or
// authentication step, calls the library API the way an integrator would, and records
// four events visible at the API boundary. Classify maps those events to an outcome.
// The same predicate is implemented in classifier/observability.py and in the JMRTD
// driver (Observability.java); testdata/observability-vectors.json keeps them aligned.
package classifier

// Outcome is the oracle verdict for one run.
type Outcome string

const (
	// OutcomeSilent: the call succeeded and nothing the caller can reach records the failure.
	OutcomeSilent Outcome = "silent"
	// OutcomeStatusOnly: the call succeeded; the failure is recorded only in a field of the
	// returned result, which the caller must inspect to notice it.
	OutcomeStatusOnly Outcome = "status_only"
	// OutcomeSurfaced: the call returned an error or threw, so the caller cannot proceed unaware.
	OutcomeSurfaced Outcome = "surfaced"
	// OutcomeNotApplicable: the injected failure did not fire, so there is nothing to observe.
	OutcomeNotApplicable Outcome = "not_applicable"
	// OutcomeInvalid: the observation is self-contradictory (the step both failed and succeeded).
	OutcomeInvalid Outcome = "invalid"
)

// Observation is what a driver records for one run. Fired comes from the harness (the
// simulated peer delivered the injected failure); the other fields are what the library and
// the caller-side code report at the API boundary.
type Observation struct {
	// Fired is true when the simulated peer actually delivered the injected failure.
	Fired bool `json:"fired"`
	// Failed is true when the library reports the targeted step as failed.
	Failed bool `json:"failed"`
	// Succeeded is true when the library reports the targeted step as successful.
	Succeeded bool `json:"succeeded"`
	// ReturnedError is true when the API call returned an error or threw to the caller.
	ReturnedError bool `json:"returned_error"`
	// StatusSignal is true when a field of the returned result records the failure.
	StatusSignal bool `json:"status_signal"`
}

// Classify applies the oracle. Invalid and not-applicable are decided before any score is
// assigned, so a run whose injection never fired cannot read as fail-closed. A library that
// reports success for a step the peer failed is silent unless something else surfaces it.
func Classify(o Observation) Outcome {
	switch {
	case o.Failed && o.Succeeded:
		return OutcomeInvalid
	case !o.Fired:
		return OutcomeNotApplicable
	case o.ReturnedError:
		return OutcomeSurfaced
	case o.StatusSignal:
		return OutcomeStatusOnly
	default:
		return OutcomeSilent
	}
}

// Score returns the ordinal score (0 silent, 1 status-only, 2 surfaced) and false for
// outcomes that carry no score.
func (o Outcome) Score() (int, bool) {
	switch o {
	case OutcomeSilent:
		return 0, true
	case OutcomeStatusOnly:
		return 1, true
	case OutcomeSurfaced:
		return 2, true
	default:
		return 0, false
	}
}

// ScorePtr returns the score for JSON output (nil when the outcome carries no score).
func (o Outcome) ScorePtr() *int {
	s, ok := o.Score()
	if !ok {
		return nil
	}
	return &s
}

// Meaning is a one-line description for run artifacts.
func (o Outcome) Meaning() string {
	switch o {
	case OutcomeSilent:
		return "silent: call succeeded, failure not reachable by the caller"
	case OutcomeStatusOnly:
		return "status-only: call succeeded, failure recorded in a returned status field"
	case OutcomeSurfaced:
		return "surfaced: error returned or thrown to the caller"
	case OutcomeNotApplicable:
		return "not applicable: injected failure did not fire"
	default:
		return "invalid: library reported the step as both failed and successful"
	}
}
