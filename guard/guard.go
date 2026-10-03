// Package guard is the caller-side mitigation the oracle evaluates: after a gmrtd
// ReadDocument call returns, it turns a failure the library only recorded in the
// session into an error the caller cannot miss.
package guard

import (
	"errors"
	"fmt"

	"github.com/gmrtd/gmrtd/document"
)

// Mechanism names a negotiation or authentication step whose failure must not be ignored.
type Mechanism string

const (
	PACE Mechanism = "PACE"
	CA   Mechanism = "CA"
	AA   Mechanism = "AA"
)

// ErrRecordedFailure wraps every error the guard returns.
var ErrRecordedFailure = errors.New("guard: recorded failure")

// Require returns an error when session records a failure of any listed mechanism.
func Require(session *document.Session, mechanisms ...Mechanism) error {
	if session == nil {
		return fmt.Errorf("%w: no session", ErrRecordedFailure)
	}
	for _, m := range mechanisms {
		var err error
		switch m {
		case PACE:
			err = session.PaceErr
		case CA:
			err = session.ChipAuthErr
		case AA:
			err = session.ActiveAuthErr
		default:
			return fmt.Errorf("guard: unknown mechanism %q", m)
		}
		if err != nil {
			return fmt.Errorf("%w: %s: %v", ErrRecordedFailure, m, err)
		}
	}
	return nil
}
