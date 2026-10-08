package chipauth

// T63: deterministic check for D5 (ECDH shared secret not left-padded to the field size) in one gmrtd
// release. The file is copied into the release's chipauth package and run there, so it exercises that
// release's own deriveSessionKeys. It is never part of a library build.
//
// The terminal private key is the smallest scalar d >= 1 for which the x-coordinate of d*G on P-256 has a
// leading zero byte, so the shared secret with the chip key G is that x-coordinate. The session key
// ksEnc of the release is compared with the KDF of the secret encoded at field size (BSI TR-03111 FE2OS).

import (
	"bytes"
	"crypto/elliptic"
	"fmt"
	"math/big"
	"testing"

	"github.com/gmrtd/gmrtd/cryptoutils"
)

func TestT63LeadingZeroSharedSecret(t *testing.T) {
	curve := elliptic.P256()
	size := (curve.Params().BitSize + 7) / 8
	var d int64
	var x *big.Int
	for d = 1; d < 1<<20; d++ {
		x, _ = curve.ScalarBaseMult(big.NewInt(d).Bytes())
		if len(x.Bytes()) < size {
			break
		}
	}
	if len(x.Bytes()) >= size {
		t.Fatal("no scalar with a leading zero x-coordinate found")
	}
	g := curve.Params()
	chipPub := cryptoutils.NewEcPoint(g.Gx.Bytes(), g.Gy.Bytes())
	term := cryptoutils.EcKeypair{Pri: big.NewInt(d).Bytes()}
	alg := &CaAlgorithmInfo{cipherAlg: cryptoutils.AES, keySizeBits: 128}

	ksEnc, _ := deriveSessionKeys(&curve, term, chipPub, alg)

	padded := make([]byte, size)
	x.FillBytes(padded)
	want := cryptoutils.KDF(padded, cryptoutils.KDF_COUNTER_KSENC, cryptoutils.AES, 128)
	short := cryptoutils.KDF(x.Bytes(), cryptoutils.KDF_COUNTER_KSENC, cryptoutils.AES, 128)

	verdict := "D5_ABSENT"
	switch {
	case bytes.Equal(ksEnc, short) && !bytes.Equal(ksEnc, want):
		verdict = "D5_PRESENT"
	case !bytes.Equal(ksEnc, want):
		verdict = "OTHER"
	}
	fmt.Printf("T63 d=%d secret_len=%d verdict=%s\n", d, len(x.Bytes()), verdict)
}
