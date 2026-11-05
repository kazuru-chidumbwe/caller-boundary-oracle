//go:build gmrtd_sweep_authentic

package gmrtdrun_test

import (
	"testing"

	"github.com/gmrtd/gmrtd/password"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/guard"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/internal/gmrtdrun"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/simulator"
)

// TestTrustedChip checks the trusted-chain chip and the RequireAuthenticDocument arm (U1) before
// any measured run: the positive controls must read without error, so a refusal in the measured
// cells is the reaction to the injected fault and not to the fixture.
func TestTrustedChip(t *testing.T) {
	pass, err := password.NewPasswordMrzi("L898902C", "690806", "940623")
	if err != nil {
		t.Fatal(err)
	}
	csca := simulator.TrustedCSCA()
	cases := []struct {
		name      string
		mech      guard.Mechanism
		cfg       simulator.ChipConfig
		csca      []byte
		require   bool
		wantErr   bool
		wantOK    bool // targeted mechanism succeeded
		wantFired bool
	}{
		{"no-chip-auth", guard.AA, simulator.ChipConfig{Trusted: true}, csca, true, false, false, false},
		{"aa-ok", guard.AA, simulator.ChipConfig{Trusted: true, Dg15Hex: "00"}, csca, true, false, true, false},
		{"ca-ok", guard.CA, simulator.ChipConfig{Trusted: true, Dg14Hex: "00"}, csca, true, false, true, false},
		{"aa-fail", guard.AA, simulator.ChipConfig{Trusted: true, Dg15Hex: "00", AaSW: "6300"}, csca, true, true, false, true},
		{"ca-fail", guard.CA, simulator.ChipConfig{Trusted: true, Dg14Hex: "00", CaSW: "6A80"}, csca, true, true, false, true},
		{"dual-aa-fail-ca-ok", guard.AA, simulator.ChipConfig{Trusted: true, Dual: true, AaSW: "6300"}, csca, true, false, false, true},
		{"dual-both-ok", guard.AA, simulator.ChipConfig{Trusted: true, Dual: true}, csca, true, false, true, false},
		{"dual-both-fail", guard.AA, simulator.ChipConfig{Trusted: true, Dual: true, AaSW: "6300", CaSW: "6A80"}, csca, true, true, false, true},
		{"aa-ok-no-csca", guard.AA, simulator.ChipConfig{Trusted: true, Dg15Hex: "00"}, nil, true, true, true, false},
		{"aa-fail-default", guard.AA, simulator.ChipConfig{Trusted: true, Dg15Hex: "00", AaSW: "6300"}, csca, false, false, false, true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			chip := simulator.NewDocumentChip(c.cfg, pass)
			res, err := gmrtdrun.Run(c.mech, chip, pass, gmrtdrun.Options{CSCA: c.csca, RequireAuthentic: c.require})
			if err != nil {
				t.Fatal(err)
			}
			o := res.Observation
			if (res.ReadErr != "") != c.wantErr || o.Succeeded != c.wantOK || o.Fired != c.wantFired {
				t.Fatalf("readErr=%q succeeded=%v fired=%v chipAuthErr=%q activeAuthErr=%q; want err=%v ok=%v fired=%v",
					res.ReadErr, o.Succeeded, o.Fired, res.ChipAuthErr, res.ActiveAuthErr, c.wantErr, c.wantOK, c.wantFired)
			}
		})
	}
}
