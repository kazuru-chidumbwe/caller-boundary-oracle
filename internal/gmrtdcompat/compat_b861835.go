//go:build gmrtd_b861835

package gmrtdcompat

import (
	"github.com/gmrtd/gmrtd/cms"
	"github.com/gmrtd/gmrtd/iso7816"
	"github.com/gmrtd/gmrtd/reader"
)

// Commit is the gmrtd commit this binary is built against (v1.3.2).
const Commit = "b861835cb0c5937b8ec4c77a0e00326974f033f2"

type quietStatus struct{}

func (quietStatus) Status(reader.Status) {}

// NewReader returns a gmrtd reader with an empty CSCA pool. allowBacFallback calls
// AllowBacFallbackOnPaceError, the caller opt-in added in v1.1.3.
func NewReader(nfc *iso7816.NfcSession, allowBacFallback bool) (*reader.Reader, error) {
	r := reader.NewReader(quietStatus{}, nfc, &cms.GenericCertPool{})
	if allowBacFallback {
		r.AllowBacFallbackOnPaceError()
	}
	return r, nil
}
