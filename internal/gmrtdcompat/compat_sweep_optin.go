//go:build gmrtd_sweep_optin

package gmrtdcompat

import (
	"github.com/gmrtd/gmrtd/cms"
	"github.com/gmrtd/gmrtd/iso7816"
	"github.com/gmrtd/gmrtd/reader"
)

// Commit is set at build time (-ldflags -X) to the gmrtd release under test in the version sweep.
var Commit = "unknown"

type quietStatus struct{}

func (quietStatus) Status(reader.Status) {}

// NewReader returns a gmrtd reader with an empty CSCA pool; allowBacFallback uses the opt-in (v1.1.3 on).
func NewReader(nfc *iso7816.NfcSession, allowBacFallback bool) (*reader.Reader, error) {
	r := reader.NewReader(quietStatus{}, nfc, &cms.GenericCertPool{})
	if allowBacFallback {
		r.AllowBacFallbackOnPaceError()
	}
	return r, nil
}
