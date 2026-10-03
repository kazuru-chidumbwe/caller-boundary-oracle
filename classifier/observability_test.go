package classifier

import (
	"encoding/json"
	"os"
	"testing"
)

type vector struct {
	ID       string      `json:"id"`
	Input    Observation `json:"input"`
	Outcome  Outcome     `json:"outcome"`
	Score    *int        `json:"score"`
	Scenario string      `json:"scenario"`
}

func loadVectors(t *testing.T) []vector {
	t.Helper()
	raw, err := os.ReadFile("../testdata/observability-vectors.json")
	if err != nil {
		t.Fatal(err)
	}
	var rows []vector
	if err := json.Unmarshal(raw, &rows); err != nil {
		t.Fatal(err)
	}
	if len(rows) == 0 {
		t.Fatal("no vectors")
	}
	return rows
}

func TestSharedVectors(t *testing.T) {
	for _, v := range loadVectors(t) {
		got := Classify(v.Input)
		if got != v.Outcome {
			t.Errorf("%s: outcome %q want %q", v.ID, got, v.Outcome)
		}
		score := got.ScorePtr()
		switch {
		case score == nil && v.Score != nil, score != nil && v.Score == nil:
			t.Errorf("%s: score presence mismatch", v.ID)
		case score != nil && *score != *v.Score:
			t.Errorf("%s: score %d want %d", v.ID, *score, *v.Score)
		}
	}
}

// Every combination of the five events maps to exactly one outcome.
func TestTotal(t *testing.T) {
	for i := 0; i < 32; i++ {
		o := Observation{Fired: i&1 != 0, Failed: i&2 != 0, Succeeded: i&4 != 0, ReturnedError: i&8 != 0, StatusSignal: i&16 != 0}
		if Classify(o) == "" {
			t.Fatalf("no outcome for %+v", o)
		}
	}
}

// A run whose injection never fired must not read as fail-closed, even if some other
// error reached the caller.
func TestNotFiredIsNotSurfaced(t *testing.T) {
	got := Classify(Observation{Fired: false, Failed: true, ReturnedError: true})
	if got != OutcomeNotApplicable {
		t.Fatalf("got %q", got)
	}
}
