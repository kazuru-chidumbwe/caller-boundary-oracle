package profile

import (
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

type MRZ struct {
	DocumentNumber string `json:"document_number"`
	DateOfBirth    string `json:"date_of_birth"`
	DateOfExpiry   string `json:"date_of_expiry"`
}

type Injection struct {
	PaceFailOn string `json:"pace_fail_on"`
	PaceSW     string `json:"pace_sw"`
	// PaceChannel selects how PACE fails at the APDU boundary:
	//   "" / "sw" (default): return configured pace_sw (honest synthetic chip).
	//   "timeout": brief delay then empty response (timed exchange abstraction).
	//   "no_response": empty frame / incomplete exchange (jammed mid-handshake).
	//   "transport_abort": empty response treated as hard transport failure.
	// Channel modes are lab-only synthetic abstractions — not RF/NFC fidelity.
	PaceChannel string `json:"pace_channel,omitempty"`
	Notes       string `json:"notes"`
}

type CAInjection struct {
	CaFailOn string `json:"ca_fail_on"`
	CaSW     string `json:"ca_sw"`
	Notes    string `json:"notes"`
}

type AAInjection struct {
	AaFailOn string `json:"aa_fail_on"`
	AaSW     string `json:"aa_sw"`
	// AaBadSignature (trusted chip only): answer INTERNAL AUTHENTICATE with 9000 and a signature
	// that does not verify (the real signature with one byte changed).
	AaBadSignature bool   `json:"aa_bad_signature,omitempty"`
	Notes          string `json:"notes"`
}

type TAInjection struct {
	TaFailOn string `json:"ta_fail_on"`
	TaSW     string `json:"ta_sw"`
	Notes    string `json:"notes"`
}

// Vsmartcard configures the independent vsmartcard chip (tools/vsmartcard/emrtd_card.py).
type Vsmartcard struct {
	Dg15 bool   `json:"dg15,omitempty"`
	AaSW string `json:"aa_sw,omitempty"`
	// CardAccess is "pace-only" (default) or "npa" (the nPA card's TA, CA and PACE infos).
	CardAccess string `json:"card_access,omitempty"`
	// PaceSW and PaceStep fail one PACE step: "mse" (first MSE:Set AT) or "ga1" to "ga4".
	PaceSW   string `json:"pace_sw,omitempty"`
	PaceStep string `json:"pace_step,omitempty"`
}

type Profile struct {
	// Peer selects the chip: "" for the harness simulator, "vsmartcard" for the independent card.
	Peer          string      `json:"peer,omitempty"`
	Vsmartcard    Vsmartcard  `json:"vsmartcard,omitempty"`
	ID            string      `json:"id"`
	Name          string      `json:"name"`
	Mechanism     string      `json:"mechanism"`
	Condition     string      `json:"condition"`
	Tier          string      `json:"tier"`
	MRZ           MRZ         `json:"mrz"`
	CardAccessHex string      `json:"card_access_hex"`
	Dg14HexPath   string      `json:"dg14_hex_path,omitempty"`
	Dg15HexPath   string      `json:"dg15_hex_path,omitempty"`
	Injection     Injection   `json:"injection,omitempty"`
	CAInjection   CAInjection `json:"ca_injection,omitempty"`
	AAInjection   AAInjection `json:"aa_injection,omitempty"`
	TAInjection   TAInjection `json:"ta_injection,omitempty"`
	// Dual serves both DG14 and DG15 on the trusted chip (one mechanism fails, the other may
	// succeed). Only meaningful with the trusted chain; the harness chip serves one group.
	Dual bool `json:"dual,omitempty"`
	// TrustedChain asks tools/chip_broker.py to start chip-serve with -trusted-chain.
	TrustedChain bool `json:"trusted_chain,omitempty"`
	// PeerSupport documents asymmetric mechanisms (e.g. TA: gmrtd unsupported).
	PeerSupport map[string]string `json:"peer_support,omitempty"`
}

func Load(path string) (*Profile, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read profile: %w", err)
	}
	var p Profile
	if err := json.Unmarshal(raw, &p); err != nil {
		return nil, fmt.Errorf("parse profile: %w", err)
	}
	if p.ID == "" || p.MRZ.DocumentNumber == "" {
		return nil, fmt.Errorf("profile missing required fields (id, mrz)")
	}
	return &p, nil
}

func LoadHexFile(path string) ([]byte, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	s := strings.Map(func(r rune) rune {
		if r == ' ' || r == '\n' || r == '\r' || r == '\t' {
			return -1
		}
		return r
	}, string(raw))
	return hex.DecodeString(s)
}

// VsmartcardPaceFaultPoint names the PACE step a vsmartcard profile fails ("" for none):
// "mse" is "PACE/mse_set_at", "gaN" is "PACE/general_authenticate_stepN".
func VsmartcardPaceFaultPoint(step string) string {
	switch {
	case step == "":
		return ""
	case step == "mse":
		return "PACE/mse_set_at"
	case len(step) == 3 && step[:2] == "ga":
		return "PACE/general_authenticate_step" + step[2:]
	}
	return "PACE/" + step
}
