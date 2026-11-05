// Package gmrtdrun drives gmrtd's shipped ReadDocument once against a synthetic chip and
// records the caller-boundary observation for one targeted mechanism.
package gmrtdrun

import (
	"github.com/gmrtd/gmrtd/document"
	"github.com/gmrtd/gmrtd/iso7816"
	"github.com/gmrtd/gmrtd/password"
	"github.com/gmrtd/gmrtd/utils"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/classifier"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/guard"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/internal/gmrtdcompat"
)

// Options are the two caller choices the oracle compares.
type Options struct {
	// AllowBacFallback calls AllowBacFallbackOnPaceError (gmrtd v1.1.3 opt-in).
	AllowBacFallback bool
	// Guard applies guard.Require for the targeted mechanism after ReadDocument returns.
	Guard bool
	// CSCA, when set, is loaded into the reader's CSCA pool (trusted-chain chip).
	CSCA []byte
	// RequireAuthentic calls RequireAuthenticDocument (gmrtd v1.4.0 opt-in).
	RequireAuthentic bool
}

// TraceEntry is one APDU exchange from gmrtd's APDU log.
type TraceEntry struct {
	Label   string `json:"label"`
	CApdu   string `json:"capdu"`
	RApdu   string `json:"rapdu"`
	Success bool   `json:"success"`
}

// Result is everything a run artifact records about the call.
type Result struct {
	Observation   classifier.Observation `json:"observation"`
	ReadErr       string                 `json:"read_document_err"`
	GuardErr      string                 `json:"guard_err"`
	PaceErr       string                 `json:"pace_err"`
	BacErr        string                 `json:"bac_err"`
	BacSuccess    bool                   `json:"bac_success"`
	ChipAuthErr   string                 `json:"chip_auth_err"`
	ActiveAuthErr string                 `json:"active_auth_err"`
	Trace         []TraceEntry           `json:"trace"`
}

// Chip is a simulated peer that can report whether it delivered the injected failure.
type Chip interface {
	iso7816.Transceiver
	FaultDelivered(mechanism string) bool
}

// Run calls ReadDocument once and observes mechanism.
func Run(mechanism guard.Mechanism, chip Chip, pass *password.Password, opts Options) (Result, error) {
	nfc := iso7816.NewNfcSession(chip)
	r, err := gmrtdcompat.NewReaderAuth(nfc, opts.AllowBacFallback, opts.CSCA, opts.RequireAuthentic)
	if err != nil {
		return Result{}, err
	}
	docEx, apduLog, readErr := r.ReadDocument(pass, nil, nil)

	var res Result
	res.ReadErr = errString(readErr)
	var session *document.Session
	if docEx != nil {
		session = &docEx.Session
		res.PaceErr = errString(session.PaceErr)
		res.BacErr = errString(session.BacErr)
		res.BacSuccess = session.BacResult != nil && session.BacResult.Success
		res.ChipAuthErr = errString(session.ChipAuthErr)
		res.ActiveAuthErr = errString(session.ActiveAuthErr)
	}
	var guardErr error
	if opts.Guard && readErr == nil {
		guardErr = guard.Require(session, mechanism)
		res.GuardErr = errString(guardErr)
	}

	failed, succeeded := stepState(mechanism, session)
	res.Observation = classifier.Observation{
		Fired:         chip.FaultDelivered(string(mechanism)),
		Failed:        failed,
		Succeeded:     succeeded,
		ReturnedError: readErr != nil || guardErr != nil,
		// The session is part of the value ReadDocument hands back to the caller.
		StatusSignal: session != nil && failed,
	}
	if apduLog == nil {
		apduLog = nfc.ApduLog()
	}
	res.Trace = buildTrace(apduLog)
	return res, nil
}

func stepState(m guard.Mechanism, s *document.Session) (failed, succeeded bool) {
	if s == nil {
		return false, false
	}
	switch m {
	case guard.PACE:
		return s.PaceErr != nil, s.PaceResult != nil && s.PaceResult.Success
	case guard.CA:
		return s.ChipAuthErr != nil, s.ChipAuthResult != nil && s.ChipAuthResult.Success
	case guard.AA:
		return s.ActiveAuthErr != nil, s.ActiveAuthResult != nil && s.ActiveAuthResult.Success
	}
	return false, false
}

func buildTrace(log *iso7816.ApduLog) []TraceEntry {
	if log == nil {
		return nil
	}
	entries := log.AllEntries()
	out := make([]TraceEntry, 0, len(entries))
	for _, e := range entries {
		ok := len(e.Rx) >= 2 && e.Rx[len(e.Rx)-2] == 0x90 && e.Rx[len(e.Rx)-1] == 0x00
		out = append(out, TraceEntry{Label: e.Desc, CApdu: utils.BytesToHex(e.Tx), RApdu: utils.BytesToHex(e.Rx), Success: ok})
	}
	return out
}

func errString(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}
