//go:build gmrtd_sweep_typed

package gmrtdcompat

import (
	"errors"

	"github.com/gmrtd/gmrtd/cms"
	"github.com/gmrtd/gmrtd/iso7816"
	"github.com/gmrtd/gmrtd/reader"
)

// Commit is set at build time (-ldflags -X) to the gmrtd release under test in the version sweep.
var Commit = "unknown"

// ErrNoOptIn is returned when a run asks for the BAC-fallback opt-in, which this release lacks.
var ErrNoOptIn = errors.New("this gmrtd release has no BAC-fallback opt-in")

type quietStatus struct{}

func (quietStatus) Status(reader.Status) {}

// NewReader returns a gmrtd reader with an empty CSCA pool (releases with a typed status callback).
func NewReader(nfc *iso7816.NfcSession, allowBacFallback bool) (*reader.Reader, error) {
	if allowBacFallback {
		return nil, ErrNoOptIn
	}
	return reader.NewReader(quietStatus{}, nfc, &cms.GenericCertPool{}), nil
}
