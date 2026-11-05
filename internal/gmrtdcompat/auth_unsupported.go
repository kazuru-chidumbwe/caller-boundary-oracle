//go:build !gmrtd_sweep_authentic

package gmrtdcompat

import (
	"errors"

	"github.com/gmrtd/gmrtd/iso7816"
	"github.com/gmrtd/gmrtd/reader"
)

// ErrNoAuthentic is returned when a run asks for a trusted CSCA or RequireAuthenticDocument on a
// build other than gmrtd_sweep_authentic (gmrtd v1.4.0 on).
var ErrNoAuthentic = errors.New("this build has no trusted-CSCA or RequireAuthenticDocument support")

// NewReaderAuth is NewReader when no CSCA and no RequireAuthenticDocument is asked for.
func NewReaderAuth(nfc *iso7816.NfcSession, allowBacFallback bool, csca []byte, requireAuthentic bool) (*reader.Reader, error) {
	if csca != nil || requireAuthentic {
		return nil, ErrNoAuthentic
	}
	return NewReader(nfc, allowBacFallback)
}
