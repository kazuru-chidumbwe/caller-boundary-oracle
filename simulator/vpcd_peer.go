package simulator

import (
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/gmrtd/gmrtd/iso7816"
)

// vpcd control messages (one byte, sent with length 1).
const (
	vpcdPowerOff = 0x00
	vpcdPowerOn  = 0x01
	vpcdGetATR   = 0x04
)

// VsmartcardConfig selects the profile the independent vsmartcard chip serves.
type VsmartcardConfig struct {
	// ProfilePath is the profile JSON; the card reads its "vsmartcard" object (what to serve,
	// which step to fail).
	ProfilePath string
}

// VsmartcardPeer runs tools/vsmartcard/emrtd_card.py and acts as its reader: it accepts
// the card's connection and exchanges length-prefixed APDUs (the vpcd socket protocol).
// The card process needs vsmartcard and the OpenPACE Python bindings on PYTHONPATH.
type VsmartcardPeer struct {
	cfg     VsmartcardConfig
	cmd     *exec.Cmd
	conn    net.Conn
	ln      net.Listener
	atr     []byte
	report  string
	lastErr error
}

// StartVsmartcard launches the card script from repoRoot and waits for it to connect.
func StartVsmartcard(repoRoot string, cfg VsmartcardConfig) (*VsmartcardPeer, error) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return nil, err
	}
	port := ln.Addr().(*net.TCPAddr).Port
	rf, err := os.CreateTemp("", "vsmartcard-report-*.json")
	if err != nil {
		ln.Close()
		return nil, err
	}
	report := rf.Name()
	rf.Close()
	args := []string{filepath.Join(repoRoot, "tools", "vsmartcard", "emrtd_card.py"), "--port", fmt.Sprint(port),
		"--profile", cfg.ProfilePath, "--report", report}
	if lvl := os.Getenv("VSMARTCARD_LOG_LEVEL"); lvl != "" {
		args = append(args, "--log-level", lvl)
	}
	cmd := exec.Command("python3", args...)
	cmd.Stdout = os.Stderr
	cmd.Stderr = os.Stderr
	if err := cmd.Start(); err != nil {
		ln.Close()
		return nil, fmt.Errorf("start vsmartcard card: %w", err)
	}
	p := &VsmartcardPeer{cfg: cfg, cmd: cmd, ln: ln, report: report}
	if tl, ok := ln.(*net.TCPListener); ok {
		_ = tl.SetDeadline(time.Now().Add(30 * time.Second))
	}
	conn, err := ln.Accept()
	if err != nil {
		p.Close()
		return nil, fmt.Errorf("vsmartcard card did not connect: %w", err)
	}
	p.conn = conn
	if err := p.send([]byte{vpcdPowerOn}); err != nil {
		p.Close()
		return nil, err
	}
	if err := p.send([]byte{vpcdGetATR}); err != nil {
		p.Close()
		return nil, err
	}
	if p.atr, err = p.recv(); err != nil {
		p.Close()
		return nil, fmt.Errorf("read ATR: %w", err)
	}
	return p, nil
}

func (p *VsmartcardPeer) send(msg []byte) error {
	buf := make([]byte, 2+len(msg))
	binary.BigEndian.PutUint16(buf, uint16(len(msg)))
	copy(buf[2:], msg)
	_, err := p.conn.Write(buf)
	return err
}

func (p *VsmartcardPeer) recv() ([]byte, error) {
	_ = p.conn.SetReadDeadline(time.Now().Add(30 * time.Second))
	var hdr [2]byte
	if _, err := io.ReadFull(p.conn, hdr[:]); err != nil {
		return nil, err
	}
	msg := make([]byte, binary.BigEndian.Uint16(hdr[:]))
	if _, err := io.ReadFull(p.conn, msg); err != nil {
		return nil, err
	}
	return msg, nil
}

var _ iso7816.Transceiver = (*VsmartcardPeer)(nil)

// Transceive forwards the encoded command APDU to the card and returns its response.
// A transport failure is returned as an empty response, which gmrtd treats as an error.
func (p *VsmartcardPeer) Transceive(_, ins, _, _ int, _ []byte, _ int, encodedData []byte) []byte {
	if err := p.send(encodedData); err != nil {
		p.lastErr = err
		return nil
	}
	rsp, err := p.recv()
	if err != nil {
		p.lastErr = err
		return nil
	}
	return rsp
}

// FaultDelivered reports whether the card sent the injected failure for mechanism, as recorded
// in the card's delivered-fault report.
func (p *VsmartcardPeer) FaultDelivered(mechanism string) bool {
	data, err := os.ReadFile(p.report)
	if err != nil {
		return false
	}
	var r struct {
		FaultDelivered map[string]bool `json:"fault_delivered"`
	}
	if json.Unmarshal(data, &r) != nil {
		return false
	}
	return r.FaultDelivered[mechanism]
}

// TransportError returns the first socket error seen, if any.
func (p *VsmartcardPeer) TransportError() error { return p.lastErr }

// Close powers the card down and stops the card process.
func (p *VsmartcardPeer) Close() {
	if p.conn != nil {
		_ = p.send([]byte{vpcdPowerOff})
		_ = p.conn.Close()
	}
	if p.ln != nil {
		_ = p.ln.Close()
	}
	if p.cmd != nil && p.cmd.Process != nil {
		_ = p.cmd.Process.Kill()
		_ = p.cmd.Wait()
	}
}
