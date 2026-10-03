package simulator

import (
	"encoding/binary"
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

// VsmartcardConfig selects what the independent vsmartcard chip serves.
type VsmartcardConfig struct {
	// Dg15 serves DG15 so readers attempt Active Authentication.
	Dg15 bool
	// AaSW fails INTERNAL AUTHENTICATE with this status word (hex, empty for no fault).
	AaSW string
	// CardAccess selects the chip's EF.CardAccess ("" or "pace-only", or "npa").
	CardAccess string
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
	aaSent  bool
	lastErr error
}

// StartVsmartcard launches the card script from repoRoot and waits for it to connect.
func StartVsmartcard(repoRoot string, cfg VsmartcardConfig) (*VsmartcardPeer, error) {
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return nil, err
	}
	port := ln.Addr().(*net.TCPAddr).Port
	args := []string{filepath.Join(repoRoot, "tools", "vsmartcard", "emrtd_card.py"), "--port", fmt.Sprint(port)}
	if cfg.Dg15 {
		args = append(args, "--dg15")
	}
	if cfg.AaSW != "" {
		args = append(args, "--aa-sw", cfg.AaSW)
	}
	if cfg.CardAccess != "" {
		args = append(args, "--card-access", cfg.CardAccess)
	}
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
	p := &VsmartcardPeer{cfg: cfg, cmd: cmd, ln: ln}
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
	if byte(ins) == iso7816.INS_INTERNAL_AUTHENTICATE {
		p.aaSent = true
	}
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

// FaultDelivered reports whether the configured fault was exercised. Only Active
// Authentication can be failed on this chip; PACE and CA always run unmodified.
func (p *VsmartcardPeer) FaultDelivered(mechanism string) bool {
	return mechanism == "AA" && p.cfg.AaSW != "" && p.aaSent
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
