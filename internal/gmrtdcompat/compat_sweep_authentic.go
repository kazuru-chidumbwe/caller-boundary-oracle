//go:build gmrtd_sweep_authentic

package gmrtdcompat

import (
	"github.com/gmrtd/gmrtd/cms"
	"github.com/gmrtd/gmrtd/iso7816"
	"github.com/gmrtd/gmrtd/reader"
)

// Commit is set at build time (-ldflags -X) to the gmrtd release under test (v1.4.0 on).
var Commit = "unknown"

type quietStatus struct{}

func (quietStatus) Status(reader.Status) {}

// NewReader returns a gmrtd reader with an empty CSCA pool; allowBacFallback uses the opt-in.
func NewReader(nfc *iso7816.NfcSession, allowBacFallback bool) (*reader.Reader, error) {
	return NewReaderAuth(nfc, allowBacFallback, nil, false)
}

// NewReaderAuth also loads csca (DER) into the CSCA pool when given, and calls
// RequireAuthenticDocument (gmrtd v1.4.0, PR #537) when requireAuthentic is set.
func NewReaderAuth(nfc *iso7816.NfcSession, allowBacFallback bool, csca []byte, requireAuthentic bool) (*reader.Reader, error) {
	pool := &cms.GenericCertPool{}
	if csca != nil {
		if err := pool.Add(csca); err != nil {
			return nil, err
		}
	}
	r := reader.NewReader(quietStatus{}, nfc, pool)
	if allowBacFallback {
		r.AllowBacFallbackOnPaceError()
	}
	if requireAuthentic {
		r.RequireAuthenticDocument()
	}
	return r, nil
}
