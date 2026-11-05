package simulator

import (
	"crypto/ecdh"
	"crypto/rsa"
	"crypto/sha1"
	"crypto/x509"
	_ "embed"
	"fmt"
	"math/big"
	"strings"

	"github.com/gmrtd/gmrtd/cryptoutils"
	"github.com/gmrtd/gmrtd/utils"
)

// Trusted-chain chip (profiles/generate_trusted_fixtures.py): a document a reader can verify end
// to end. Its EF.SOD is signed by a Document Signer issued by a synthetic CSCA (TrustedCSCA), and
// the chip holds the private keys for the DG14 Chip Authentication key and the DG15 Active
// Authentication key, so CA and AA succeed unless a profile injects a failure. The success paths
// below are active only on a trusted chip; the harness chip is unchanged.

//go:embed fixtures/trusted/csca.hex
var trustedCscaHex string

//go:embed fixtures/trusted/dg1.hex
var trustedDg1Hex string

//go:embed fixtures/trusted/dg2.hex
var trustedDg2Hex string

//go:embed fixtures/trusted/dg14.hex
var trustedDg14Hex string

//go:embed fixtures/trusted/dg15.hex
var trustedDg15Hex string

//go:embed fixtures/trusted/ca-key.hex
var trustedCaKeyHex string

//go:embed fixtures/trusted/aa-key.hex
var trustedAaKeyHex string

//go:embed fixtures/trusted/sod-dg1-dg2.hex
var trustedSodDg1Dg2Hex string

//go:embed fixtures/trusted/sod-dg1-dg2-dg14.hex
var trustedSodDg14Hex string

//go:embed fixtures/trusted/sod-dg1-dg2-dg15.hex
var trustedSodDg15Hex string

//go:embed fixtures/trusted/sod-dg1-dg2-dg14-dg15.hex
var trustedSodDg14Dg15Hex string

func hx(s string) []byte { return utils.HexToBytes(strings.TrimSpace(s)) }

// TrustedCSCA returns the DER certificate a reader must trust to verify the trusted chip.
func TrustedCSCA() []byte { return hx(trustedCscaHex) }

// trustedFiles returns the files of the trusted chip: DG1, DG2, the DG14 and/or DG15 asked for,
// and the EF.SOD that lists exactly those groups.
func trustedFiles(withDg14, withDg15 bool) (files map[uint16][]byte, comTags []byte) {
	files = map[uint16][]byte{
		fileIDEFDIR: bytesClone(baseEfDir),
		fileIDDG1:   hx(trustedDg1Hex),
		fileIDDG2:   hx(trustedDg2Hex),
	}
	comTags = []byte{0x61, 0x75}
	sod := trustedSodDg1Dg2Hex
	switch {
	case withDg14 && withDg15:
		sod = trustedSodDg14Dg15Hex
	case withDg14:
		sod = trustedSodDg14Hex
	case withDg15:
		sod = trustedSodDg15Hex
	}
	if withDg14 {
		files[fileIDDG14] = hx(trustedDg14Hex)
		comTags = append(comTags, 0x6E)
	}
	if withDg15 {
		files[fileIDDG15] = hx(trustedDg15Hex)
		comTags = append(comTags, 0x6F)
	}
	files[fileIDEFCOM] = efCom(comTags...)
	files[fileIDEFSOD] = hx(sod)
	return files, comTags
}

func trustedAaKey() (*rsa.PrivateKey, error) {
	return x509.ParsePKCS1PrivateKey(hx(trustedAaKeyHex))
}

func trustedCaKey() (*ecdh.PrivateKey, error) {
	return ecdh.P256().NewPrivateKey(hx(trustedCaKeyHex))
}

// aaSign answers INTERNAL AUTHENTICATE: ISO/IEC 9796-2 digital signature scheme 1 with SHA-1
// (ICAO 9303 Part 11, 6.1), F = 6A || M1 || SHA-1(M1 || RND.IFD) || BC, signature F^d mod n.
func aaSign(key *rsa.PrivateKey, rndIfd []byte) []byte {
	k := key.N.BitLen() / 8
	m1 := make([]byte, k-1-sha1.Size-1)
	for i := range m1 {
		m1[i] = byte(0x5A ^ i)
	}
	h := sha1.Sum(append(append([]byte{}, m1...), rndIfd...))
	f := append([]byte{0x6A}, m1...)
	f = append(f, h[:]...)
	f = append(f, 0xBC)
	s := new(big.Int).Exp(new(big.Int).SetBytes(f), key.D, key.N)
	return s.FillBytes(make([]byte, k))
}

// caKeyAgreement takes the GENERAL AUTHENTICATE data (7C { 80 terminal ephemeral public key })
// and returns the 3DES session keys of id-CA-ECDH-3DES-CBC-CBC (ICAO 9303 Part 11, 6.2 and 9.7.1).
func caKeyAgreement(key *ecdh.PrivateKey, data []byte) (ksEnc, ksMac []byte, err error) {
	pt, err := dynAuthObject(data, 0x80)
	if err != nil {
		return nil, nil, err
	}
	pub, err := ecdh.P256().NewPublicKey(pt)
	if err != nil {
		return nil, nil, fmt.Errorf("terminal key: %w", err)
	}
	secret, err := key.ECDH(pub)
	if err != nil {
		return nil, nil, err
	}
	ksEnc = cryptoutils.KDF(secret, cryptoutils.KDF_COUNTER_KSENC, cryptoutils.TDES, 112)
	ksMac = cryptoutils.KDF(secret, cryptoutils.KDF_COUNTER_KSMAC, cryptoutils.TDES, 112)
	return ksEnc, ksMac, nil
}

// dynAuthObject returns the value of tag inside a 7C dynamic authentication data object.
func dynAuthObject(data []byte, tag byte) ([]byte, error) {
	body, rest, err := derTLV(data, 0x7C)
	if err != nil || len(rest) != 0 {
		return nil, fmt.Errorf("dynamic authentication data: %v", err)
	}
	v, _, err := derTLV(body, tag)
	return v, err
}

func derTLV(b []byte, tag byte) (value, rest []byte, err error) {
	if len(b) < 2 || b[0] != tag {
		return nil, nil, fmt.Errorf("want tag %02X", tag)
	}
	n, off := int(b[1]), 2
	if b[1]&0x80 != 0 {
		nb := int(b[1] & 0x7F)
		if nb < 1 || nb > 2 || len(b) < 2+nb {
			return nil, nil, fmt.Errorf("bad length")
		}
		n = 0
		for _, c := range b[2 : 2+nb] {
			n = n<<8 | int(c)
		}
		off = 2 + nb
	}
	if len(b) < off+n {
		return nil, nil, fmt.Errorf("short value")
	}
	return b[off : off+n], b[off+n:], nil
}

// NewChipSM3DES starts secure messaging with fresh 3DES session keys and SSC zero, as after
// Chip Authentication (ICAO 9303 Part 11, 9.8.2).
func NewChipSM3DES(ksEnc, ksMac []byte) (*ChipSM, error) {
	encCipher, err := cryptoutils.CipherForKey(cryptoutils.TDES, ksEnc)
	if err != nil {
		return nil, err
	}
	return &ChipSM{ksEnc: ksEnc, ksMac: ksMac, ssc: make([]byte, 8), encCipher: encCipher}, nil
}
