//go:build gmrtd_8fea245

package gmrtdcompat

import (
	"errors"

	"github.com/gmrtd/gmrtd/cms"
	"github.com/gmrtd/gmrtd/iso7816"
	"github.com/gmrtd/gmrtd/reader"
)

// Commit is the gmrtd commit this binary is built against (v0.45.0).
const Commit = "8fea245048d3b4e76483d048b202ff7f5269728c"

// ErrNoOptIn is returned when a run asks for the BAC-fallback opt-in, which does not
// exist at this pin (fallback after a PACE error is unconditional here).
var ErrNoOptIn = errors.New("gmrtd 8fea245 has no BAC-fallback opt-in")

type quietStatus struct{}

func (quietStatus) Status(string) {}

// NewReader returns a gmrtd reader with an empty CSCA pool.
func NewReader(nfc *iso7816.NfcSession, allowBacFallback bool) (*reader.Reader, error) {
	if allowBacFallback {
		return nil, ErrNoOptIn
	}
	return reader.NewReader(quietStatus{}, nfc, &cms.GenericCertPool{}), nil
}
