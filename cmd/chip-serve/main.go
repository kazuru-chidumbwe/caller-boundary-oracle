// Command chip-serve exposes the harness chip simulator over the vpcd socket protocol
// (length-prefixed messages; one-byte control messages for power and ATR), the protocol
// vsmartcard cards speak. Drivers for libraries in other languages act as the reader and
// talk to this chip or to the independent vsmartcard chip through the same small transport.
//
// The process connects to the reader at -host:-port, serves one connection and, on exit,
// writes a JSON report of the faults it delivered to -report.
package main

import (
	"encoding/binary"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"os"

	"github.com/gmrtd/gmrtd/password"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/internal/profile"
	"github.com/kazuru-chidumbwe/caller-boundary-oracle/simulator"
)

const (
	ctrlPowerOff = 0x00
	ctrlPowerOn  = 0x01
	ctrlReset    = 0x02
	ctrlGetATR   = 0x04
)

// atr is a generic contactless ATR (PC/SC part 3 style, ISO 14443-4).
var atr = []byte{0x3B, 0x80, 0x80, 0x01, 0x01}

type report struct {
	FaultDelivered map[string]bool `json:"fault_delivered"`
	Sessions       int             `json:"sessions"`
}

func main() {
	profilePath := flag.String("profile", "", "chip profile JSON")
	host := flag.String("host", "127.0.0.1", "reader host")
	port := flag.Int("port", 0, "reader port")
	reportPath := flag.String("report", "", "write delivered-fault report here on exit")
	trustedChain := flag.Bool("trusted-chain", false, "serve the trusted-chain chip (CA and AA succeed unless the profile injects a failure), as gmrtd-read -trusted-chain")
	flag.Parse()

	p, err := profile.Load(*profilePath)
	if err != nil {
		fatal("profile", err)
	}
	cfg, err := simulator.ChipConfigFromProfile(p)
	if err != nil {
		fatal("profile", err)
	}
	if p.Dual && !*trustedChain {
		fatal("profile", fmt.Errorf("dual profile %s needs -trusted-chain", p.ID))
	}
	cfg.Trusted = *trustedChain
	pass, err := password.NewPasswordMrzi(p.MRZ.DocumentNumber, p.MRZ.DateOfBirth, p.MRZ.DateOfExpiry)
	if err != nil {
		fatal("password", err)
	}
	conn, err := net.Dial("tcp", net.JoinHostPort(*host, fmt.Sprint(*port)))
	if err != nil {
		fatal("connect", err)
	}
	defer conn.Close()

	rep := report{FaultDelivered: map[string]bool{}}
	var chip *simulator.DocumentChip
	// A reset starts a new chip session with the same fault injection: the injected fault is
	// a property of the chip or channel, not of one session.
	newSession := func() {
		record(chip, rep.FaultDelivered)
		chip = simulator.NewDocumentChip(cfg, pass)
		rep.Sessions++
	}
	newSession()

	err = serve(conn, func(msg []byte) ([]byte, bool) {
		if len(msg) == 1 {
			switch msg[0] {
			case ctrlPowerOn, ctrlReset:
				newSession()
			case ctrlPowerOff:
			case ctrlGetATR:
				return atr, true
			}
			return nil, false
		}
		cla, ins, p1, p2, data, le, ok := parseCommand(msg)
		if !ok {
			return []byte{0x67, 0x00}, true
		}
		return chip.Transceive(int(cla), int(ins), int(p1), int(p2), data, le, msg), true
	})
	record(chip, rep.FaultDelivered)
	if *reportPath != "" {
		raw, _ := json.Marshal(rep)
		if werr := os.WriteFile(*reportPath, raw, 0o644); werr != nil {
			fatal("report", werr)
		}
	}
	if err != nil && !errors.Is(err, io.EOF) {
		fatal("serve", err)
	}
}

func record(chip *simulator.DocumentChip, into map[string]bool) {
	if chip == nil {
		return
	}
	for _, m := range []string{"PACE", "CA", "AA"} {
		if chip.FaultDelivered(m) {
			into[m] = true
		}
	}
}

// serve reads length-prefixed messages and writes the handler's answer when it has one.
func serve(conn net.Conn, handle func([]byte) ([]byte, bool)) error {
	var hdr [2]byte
	for {
		if _, err := io.ReadFull(conn, hdr[:]); err != nil {
			return err
		}
		msg := make([]byte, binary.BigEndian.Uint16(hdr[:]))
		if _, err := io.ReadFull(conn, msg); err != nil {
			return err
		}
		rsp, answer := handle(msg)
		if !answer {
			continue
		}
		out := make([]byte, 2+len(rsp))
		binary.BigEndian.PutUint16(out, uint16(len(rsp)))
		copy(out[2:], rsp)
		if _, err := conn.Write(out); err != nil {
			return err
		}
	}
}

// parseCommand decodes a short or extended command APDU (ISO 7816-4 cases 1 to 4).
func parseCommand(b []byte) (cla, ins, p1, p2 byte, data []byte, le int, ok bool) {
	if len(b) < 4 {
		return
	}
	cla, ins, p1, p2 = b[0], b[1], b[2], b[3]
	body := b[4:]
	switch {
	case len(body) == 0:
		return cla, ins, p1, p2, nil, 0, true
	case len(body) == 1:
		le = int(body[0])
		if le == 0 {
			le = 256
		}
		return cla, ins, p1, p2, nil, le, true
	case body[0] != 0:
		lc := int(body[0])
		if len(body) < 1+lc {
			return
		}
		data = body[1 : 1+lc]
		rest := body[1+lc:]
		if len(rest) == 1 {
			le = int(rest[0])
			if le == 0 {
				le = 256
			}
		}
		return cla, ins, p1, p2, data, le, true
	case len(body) == 3:
		le = int(binary.BigEndian.Uint16(body[1:]))
		if le == 0 {
			le = 65536
		}
		return cla, ins, p1, p2, nil, le, true
	default:
		lc := int(binary.BigEndian.Uint16(body[1:3]))
		if len(body) < 3+lc {
			return
		}
		data = body[3 : 3+lc]
		rest := body[3+lc:]
		if len(rest) == 2 {
			le = int(binary.BigEndian.Uint16(rest))
			if le == 0 {
				le = 65536
			}
		}
		return cla, ins, p1, p2, data, le, true
	}
}

func fatal(step string, err error) {
	fmt.Fprintf(os.Stderr, "chip-serve %s: %v\n", step, err)
	os.Exit(2)
}
