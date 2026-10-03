package simulator

import (
	_ "embed"
	"encoding/binary"
	"strings"

	"github.com/gmrtd/gmrtd/iso7816"
	"github.com/gmrtd/gmrtd/password"
	"github.com/gmrtd/gmrtd/utils"
)

//go:embed fixtures/dg1.hex
var dg1Hex string

//go:embed fixtures/sod-dg1.hex
var sodDg1Hex string

//go:embed fixtures/sod-dg1-dg14.hex
var sodDg1Dg14Hex string

//go:embed fixtures/sod-dg1-dg15.hex
var sodDg1Dg15Hex string

// ICAO Doc 9303 Part 10 Table 31 EF.DIR sample.
var baseEfDir = utils.HexToBytes("61094F07A000000247100161094F07A000000247200161094F07A000000247200261094F07A0000002472003")

// efCom builds EF.COM (LDS 1.7, Unicode 4.0.0) listing the given data-group tags.
func efCom(tags ...byte) []byte {
	body := append(utils.HexToBytes("5F0104303130375F3606303430303030"), 0x5C, byte(len(tags)))
	body = append(body, tags...)
	return append([]byte{0x60, byte(len(body))}, body...)
}

// File IDs read by gmrtd reader.ReadDocument.
const (
	fileIDCardAccess = uint16(0x011C)
	fileIDEFSOD      = uint16(0x011D)
	fileIDEFCOM      = uint16(0x011E)
	fileIDEFDIR      = uint16(0x2F00)
	fileIDDG1        = uint16(0x0101)
	fileIDDG14       = uint16(0x010E)
	fileIDDG15       = uint16(0x010F)
)

// ChipConfig describes one synthetic chip for a full ReadDocument call.
type ChipConfig struct {
	// CardAccessHex is the EF.CardAccess body. Empty means the file is absent (BAC-only chip).
	CardAccessHex string
	// PaceSW, PaceFailOn and PaceChannel inject a PACE failure (see PaceBacTransceiver).
	PaceSW      string
	PaceFailOn  string
	PaceChannel string
	// Dg14Hex / Dg15Hex are served when set; EF.SOD then lists exactly that data group.
	Dg14Hex string
	Dg15Hex string
	// CaSW fails Chip Authentication (MSE:Set AT/KAT under SM) with this status word.
	CaSW string
	// AaSW fails Active Authentication (INTERNAL AUTHENTICATE under SM) with this status word.
	AaSW string
}

// DocumentChip answers every APDU gmrtd's ReadDocument sends: SELECT/READ of EF.CardAccess,
// PACE (failing as configured), BAC with real secure messaging, then SM reads of EF.DIR,
// EF.SOD, EF.COM and the configured data groups, and CA or AA failing as configured.
// Files that are not configured return 6A82 so gmrtd skips them.
type DocumentChip struct {
	bac          *PaceBacTransceiver
	sm           *ChipSM
	selectedFile uint16
	haveFile     bool
	files        map[uint16][]byte
	caSW         []byte
	aaSW         []byte
	caAttempts   int
	aaAttempts   int
}

// NewDocumentChip builds a chip from cfg. At most one of Dg14Hex and Dg15Hex may be set,
// so the run exercises a single authentication mechanism.
func NewDocumentChip(cfg ChipConfig, pass *password.Password) *DocumentChip {
	paceSW := cfg.PaceSW
	if paceSW == "" {
		paceSW = "6FFF"
	}
	// EF.COM and EF.SOD list exactly the data groups served: DG1, plus DG14 or DG15.
	sod := sodDg1Hex
	comTags := []byte{0x61}
	files := map[uint16][]byte{
		fileIDEFDIR: bytesClone(baseEfDir),
		fileIDDG1:   utils.HexToBytes(strings.TrimSpace(dg1Hex)),
	}
	if cfg.CardAccessHex != "" {
		files[fileIDCardAccess] = utils.HexToBytes(cfg.CardAccessHex)
	}
	switch {
	case cfg.Dg14Hex != "":
		files[fileIDDG14] = utils.HexToBytes(cfg.Dg14Hex)
		sod = sodDg1Dg14Hex
		comTags = append(comTags, 0x6E)
	case cfg.Dg15Hex != "":
		files[fileIDDG15] = utils.HexToBytes(cfg.Dg15Hex)
		sod = sodDg1Dg15Hex
		comTags = append(comTags, 0x6F)
	}
	files[fileIDEFCOM] = efCom(comTags...)
	files[fileIDEFSOD] = utils.HexToBytes(strings.TrimSpace(sod))
	chip := &DocumentChip{
		bac:   NewPaceBacTransceiverWithChannel(paceSW, cfg.PaceFailOn, cfg.PaceChannel, pass),
		files: files,
	}
	if cfg.CaSW != "" {
		chip.caSW = utils.HexToBytes(cfg.CaSW)
	}
	if cfg.AaSW != "" {
		chip.aaSW = utils.HexToBytes(cfg.AaSW)
	}
	return chip
}

func bytesClone(b []byte) []byte {
	if b == nil {
		return nil
	}
	out := make([]byte, len(b))
	copy(out, b)
	return out
}

var _ iso7816.Transceiver = (*DocumentChip)(nil)

func (t *DocumentChip) Transceive(cla, ins, p1, p2 int, data []byte, le int, encodedData []byte) []byte {
	claB, insB, p1B, p2B := byte(cla), byte(ins), byte(p1), byte(p2)

	// After BAC, unprotected READ BINARY must fail (SM required).
	if t.sm != nil && insB == iso7816.INS_READ_BINARY && (claB&iso7816.CLA_MASK) != iso7816.CLA_MASK {
		return []byte{0x69, 0x87}
	}

	if t.sm != nil && (claB&iso7816.CLA_MASK) == iso7816.CLA_MASK {
		cmd, err := t.sm.UnwrapSmCommand(claB, insB, p1B, p2B, data)
		if err != nil {
			return []byte{0x69, 0x88}
		}
		return t.dispatchSM(cmd)
	}

	// BAC EXTERNAL AUTHENTICATE establishes chip-side secure messaging.
	if insB == iso7816.INS_EXTERNAL_AUTHENTICATE {
		rsp := t.bac.Transceive(cla, ins, p1, p2, data, le, encodedData)
		if len(rsp) >= 2 && rsp[len(rsp)-2] == 0x90 && rsp[len(rsp)-1] == 0x00 {
			if kIfd, rndIfd, rndIcc, kIcc, ok := t.bac.BacSessionMaterial(); ok {
				if sm, err := EstablishBacSm(kIfd, kIcc, rndIcc, rndIfd); err == nil {
					t.sm = sm
				}
			}
		}
		return rsp
	}

	return t.dispatchPlain(claB, insB, p1B, p2B, data, le, encodedData)
}

func (t *DocumentChip) dispatchSM(cmd *PlainCommand) []byte {
	var rsp []byte
	switch {
	case cmd.INS == iso7816.INS_MANAGE_SE && cmd.P1 == 0x41 && (cmd.P2 == 0xA4 || cmd.P2 == 0xA6):
		t.caAttempts++
		rsp = t.failOr(t.caSW)
	case cmd.INS == iso7816.INS_INTERNAL_AUTHENTICATE:
		t.aaAttempts++
		rsp = t.failOr(t.aaSW)
	default:
		rsp = t.dispatchPlain(0x00, cmd.INS, cmd.P1, cmd.P2, cmd.Data, cmd.Le, nil)
	}
	if len(rsp) < 2 {
		rsp = []byte{0x6F, 0x00}
	}
	sw := uint16(rsp[len(rsp)-2])<<8 | uint16(rsp[len(rsp)-1])
	out, err := t.sm.WrapSmResponse(sw, rsp[:len(rsp)-2])
	if err != nil {
		return []byte{0x6F, 0x00}
	}
	return out
}

// failOr returns the configured failure status word, or 6D00 when the mechanism is not
// configured to fail (the chip has no real CA/AA key material to succeed with).
func (t *DocumentChip) failOr(sw []byte) []byte {
	if len(sw) == 2 {
		return bytesClone(sw)
	}
	return []byte{0x6D, 0x00}
}

func (t *DocumentChip) dispatchPlain(cla, ins, p1, p2 byte, data []byte, le int, encodedData []byte) []byte {
	switch ins {
	case iso7816.INS_SELECT:
		return t.selectFile(p1, data)
	case iso7816.INS_READ_BINARY:
		return t.readBinary(p1, p2, le)
	case iso7816.INS_MANAGE_SE, iso7816.INS_GENERAL_AUTHENTICATE,
		iso7816.INS_GET_CHALLENGE, iso7816.INS_EXTERNAL_AUTHENTICATE:
		return t.bac.Transceive(int(cla), int(ins), int(p1), int(p2), data, le, encodedData)
	default:
		return []byte{0x6D, 0x00}
	}
}

func (t *DocumentChip) selectFile(p1 byte, data []byte) []byte {
	if p1 == 0x00 && (len(data) == 0 || (len(data) == 2 && data[0] == 0x3f && data[1] == 0x00)) {
		t.haveFile = false
		return []byte{0x90, 0x00}
	}
	if p1 == 0x04 {
		t.haveFile = false
		return []byte{0x90, 0x00}
	}
	if p1 == 0x02 && len(data) == 2 {
		fid := binary.BigEndian.Uint16(data)
		if _, ok := t.files[fid]; ok {
			t.selectedFile = fid
			t.haveFile = true
			return []byte{0x90, 0x00}
		}
		t.haveFile = false
		return []byte{0x6A, 0x82}
	}
	return []byte{0x6A, 0x86}
}

func (t *DocumentChip) readBinary(p1, p2 byte, le int) []byte {
	offset := int(p1)<<8 | int(p2)
	// ISO 7816-4: P1 b8 set means P1 b5-b1 is a short EF identifier and P2 the offset; the EF
	// becomes the current file. Every file served here has FID 0x0100 | SFI (EF.CardAccess
	// 1C, EF.SOD 1D, EF.COM 1E, DG1-DG16 01-10).
	if p1&0x80 != 0 {
		fid := uint16(0x0100) | uint16(p1&0x1F)
		if _, ok := t.files[fid]; !ok {
			t.haveFile = false
			return []byte{0x6A, 0x82}
		}
		t.selectedFile, t.haveFile = fid, true
		offset = int(p2)
	}
	if !t.haveFile {
		return []byte{0x6A, 0x82}
	}
	body := t.files[t.selectedFile]
	if offset < 0 || offset > len(body) {
		return []byte{0x6A, 0x86}
	}
	if le <= 0 {
		le = 256
	}
	end := offset + le
	if end > len(body) {
		end = len(body)
	}
	return append(bytesClone(body[offset:end]), 0x90, 0x00)
}

// SecureMessagingEstablished reports whether BAC completed and chip SM is active.
func (t *DocumentChip) SecureMessagingEstablished() bool { return t.sm != nil }

// FaultDelivered reports whether the chip sent the injected failure for mechanism
// ("PACE", "CA" or "AA") to the reader during this session.
func (t *DocumentChip) FaultDelivered(mechanism string) bool {
	switch mechanism {
	case "PACE":
		return t.bac.PaceFailureDelivered()
	case "CA":
		return len(t.caSW) == 2 && t.caAttempts > 0
	case "AA":
		return len(t.aaSW) == 2 && t.aaAttempts > 0
	}
	return false
}

// CaAttempts and AaAttempts count how often the library tried each mechanism.
func (t *DocumentChip) CaAttempts() int { return t.caAttempts }
func (t *DocumentChip) AaAttempts() int { return t.aaAttempts }
