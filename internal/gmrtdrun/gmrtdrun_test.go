package gmrtdrun_test

import (
	"os"
	"strings"
	"testing"

	"github.com/gmrtd/gmrtd/password"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/classifier"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/guard"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/internal/gmrtdcompat"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/internal/gmrtdrun"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/simulator"
)

const (
	cardAccessPace        = "31143012060A04007F0007020204020402010202010D"
	cardAccessProprietary = "31143012060A04007F00070202040204020102020120" // parameterId 32
)

func readHex(t *testing.T, path string) string {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	return strings.TrimSpace(string(b))
}

type scenario struct {
	name      string
	mechanism guard.Mechanism
	chip      simulator.ChipConfig
	opts      gmrtdrun.Options
	// want maps a gmrtd commit prefix to the expected outcome.
	want map[string]classifier.Outcome
}

// returnedErrorWant pins, per scenario and gmrtd commit, whether the call returned an error.
var returnedErrorWant = map[string]map[string]bool{
	// v1.1.3 refuses the whole read when it cannot do PACE locally; v0.45.0 continues with BAC.
	"pace-proprietary-params": {"8fea245": false, "64bd6ab": true},
}

func both(o classifier.Outcome) map[string]classifier.Outcome {
	return map[string]classifier.Outcome{"8fea245": o, "64bd6ab": o}
}

func TestScenarios(t *testing.T) {
	dg14 := readHex(t, "../../testdata/dg14/ca-v2-sample.hex")
	dg15 := readHex(t, "../../testdata/dg15/aa-rsa-sample.hex")
	pass, err := password.NewPasswordMrzi("L898902C3", "740812", "120415")
	if err != nil {
		t.Fatal(err)
	}
	pin := gmrtdcompat.Commit[:7]
	if pin == "b861835" {
		pin = "64bd6ab" // v1.3.2 is expected to behave as v1.1.3 in every scenario here
	}

	paceFail := simulator.ChipConfig{CardAccessHex: cardAccessPace, PaceSW: "6A80", PaceFailOn: "mse_set_at"}
	scenarios := []scenario{
		{"pace-fail", guard.PACE, paceFail, gmrtdrun.Options{},
			map[string]classifier.Outcome{"8fea245": classifier.OutcomeStatusOnly, "64bd6ab": classifier.OutcomeSurfaced}},
		{"pace-fail-ga", guard.PACE, simulator.ChipConfig{CardAccessHex: cardAccessPace, PaceSW: "6300", PaceFailOn: "general_authenticate"}, gmrtdrun.Options{},
			map[string]classifier.Outcome{"8fea245": classifier.OutcomeStatusOnly, "64bd6ab": classifier.OutcomeSurfaced}},
		{"pace-fail-optin", guard.PACE, paceFail, gmrtdrun.Options{AllowBacFallback: true},
			map[string]classifier.Outcome{"64bd6ab": classifier.OutcomeStatusOnly}},
		{"pace-fail-guarded", guard.PACE, paceFail, gmrtdrun.Options{Guard: true}, both(classifier.OutcomeSurfaced)},
		{"bac-only-control", guard.PACE, simulator.ChipConfig{}, gmrtdrun.Options{}, both(classifier.OutcomeNotApplicable)},
		// Nothing is injected; v1.1.3 refuses the whole read because it cannot do PACE locally.
		{"pace-proprietary-params", guard.PACE, simulator.ChipConfig{CardAccessHex: cardAccessProprietary}, gmrtdrun.Options{},
			both(classifier.OutcomeNotApplicable)},
		{"ca-fail", guard.CA, simulator.ChipConfig{Dg14Hex: dg14, CaSW: "6A80"}, gmrtdrun.Options{}, both(classifier.OutcomeStatusOnly)},
		{"ca-fail-guarded", guard.CA, simulator.ChipConfig{Dg14Hex: dg14, CaSW: "6A80"}, gmrtdrun.Options{Guard: true}, both(classifier.OutcomeSurfaced)},
		{"aa-fail", guard.AA, simulator.ChipConfig{Dg15Hex: dg15, AaSW: "6982"}, gmrtdrun.Options{}, both(classifier.OutcomeStatusOnly)},
		{"aa-fail-guarded", guard.AA, simulator.ChipConfig{Dg15Hex: dg15, AaSW: "6982"}, gmrtdrun.Options{Guard: true}, both(classifier.OutcomeSurfaced)},
	}
	for _, sc := range scenarios {
		t.Run(sc.name, func(t *testing.T) {
			want, ok := sc.want[pin]
			if !ok {
				t.Skipf("scenario does not apply at gmrtd %s", pin)
			}
			chip := simulator.NewDocumentChip(sc.chip, pass)
			res, err := gmrtdrun.Run(sc.mechanism, chip, pass, sc.opts)
			if err != nil {
				t.Fatal(err)
			}
			got := classifier.Classify(res.Observation)
			t.Logf("gmrtd %s: %s obs=%+v read_err=%q pace_err=%q ca_err=%q aa_err=%q bac=%v",
				pin, got, res.Observation, res.ReadErr, res.PaceErr, res.ChipAuthErr, res.ActiveAuthErr, res.BacSuccess)
			if got != want {
				t.Errorf("gmrtd %s: got %s want %s", pin, got, want)
			}
			if wantErr, ok := returnedErrorWant[sc.name][pin]; ok && res.Observation.ReturnedError != wantErr {
				t.Errorf("gmrtd %s: returned_error %v want %v", pin, res.Observation.ReturnedError, wantErr)
			}
		})
	}
}
